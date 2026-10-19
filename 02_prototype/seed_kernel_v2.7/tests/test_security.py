"""Security regression suite for kernel v2.0, mapped to R04 §39 (AC-01…AC-30) and invariants I1–I18.

Every test verifies system behaviour against the kernel interface; no test passes because a model
produced text. OS-level criteria (AC-09, AC-26, AC-27) are covered by `tools/check_os_isolation.py`
run in the deployment environment; here the corresponding architectural property (no path or handle
is ever returned to an agent; all TWE/approval/audit/police writes are kernel-internal) is tested.
"""
import json
import time
from pathlib import Path

import pytest

from kernel import KernelError
from kernel.audit import AuditLedger
from kernel.authz import ALLOW, DENY, AgentContext, FunctionSpec, KernelRuntime, _RuntimeToken
from kernel.loop import Kernel, Layout
from kernel.model import DummyModel

from conftest import BAD_PATCH, GOOD_EVIDENCE, GOOD_PATCH, blocker_call, call_json, patch_call


def K(root: Path, responses=None, police_model=None) -> Kernel:
    return Kernel(Layout.at(root), proposer=DummyModel(responses or []), monitor=DummyModel([]), police_model=police_model, install_signal_handlers=False)


def denied(res, reason=None):
    assert res.authz.result == DENY, res.authz
    if reason:
        assert res.authz.reason == reason, res.authz
    return res


def police_events(k):
    return k.police.events()


def last_audit(k):
    return list(k.audit.events())[-1]


def make_request(k, files=None, evidence=None):
    k.tasks.add("t1", "add mul", "add mul")
    res = k.dispatch(k.ctx_proposer, "propose_patch", {"task_id": "t1", "files": files or GOOD_PATCH, "rationale": "r", "evidence": evidence or GOOD_EVIDENCE})
    assert res.allowed, res.authz
    return res.output["request_id"]


def approve(k, rid):
    res = k.approve(rid, k.c.approval_phrase.format(request_id=rid))
    assert res.allowed, res.authz
    return res


# ---------------------------------------------------------------- 39.1 default deny (I1, I16)
def test_ac01_unassigned_function_is_denied(kernel_root):
    k = K(kernel_root)
    executed = []
    k.registry.register(FunctionSpec("frobnicate", "EXTERNAL_SYSTEM_WRITE", lambda a: ["external/x"], lambda ctx, a: executed.append(1)))
    for ctx in (k.ctx_proposer, k.ctx_human, k.ctx_police):
        denied(k.dispatch(ctx, "frobnicate", {}), "missing_permission")
    assert executed == []


def test_ac02_new_capability_denied_until_assigned(kernel_root):
    k = K(kernel_root)
    before = {pid: k.permissions.get(pid).permissions() for pid in k.permissions.all_ids()}
    k.registry.register(FunctionSpec("send_email", "EXTERNAL_COMMUNICATION", lambda a: ["external/mail"], lambda ctx, a: "sent"))
    assert all(k.permissions.get(pid).permissions() == before[pid] for pid in before)
    for pid in k.permissions.all_ids():
        denied(k.dispatch(k.runtime.context_for(pid), "send_email", {"to": "x"}), "missing_permission")


def test_ac03_unknown_function_denied_audited_policed(kernel_root):
    k = K(kernel_root)
    n_audit, n_police = len(list(k.audit.events())), len(police_events(k))
    denied(k.dispatch(k.ctx_proposer, "no_such_function", {}), "unknown_function")
    ev = last_audit(k)
    assert ev["authorization"] == "DENY" and ev["denial_reason"] == "unknown_function" and ev["agent_id"] == "proposer"
    assert len(list(k.audit.events())) == n_audit + 1 and len(police_events(k)) == n_police + 1
    assert police_events(k)[-1]["classification"] == "unauthorized_function"


# ---------------------------------------------------------------- 39.2 identity (I2, I7)
def test_ac04_agent_id_in_arguments_is_ignored_or_rejected(kernel_root):
    k = K(kernel_root)
    res = denied(k.dispatch(k.ctx_proposer, "read_audit", {"agent_id": "human"}), "identity_mismatch")
    assert last_audit(k)["agent_id"] == "proposer"
    # a matching argument does not add authority either: proposer still lacks AUDIT_READ
    denied(k.dispatch(k.ctx_proposer, "read_audit", {"agent_id": "proposer"}), "missing_permission")


def test_ac05_missing_or_forged_context_is_denied(kernel_root):
    k = K(kernel_root)
    denied(k.dispatch(None, "get_authorization_profile", {}), "unknown_identity")
    denied(k.dispatch({"agent_id": "human"}, "read_audit", {}), "unknown_identity")
    forged = AgentContext("human", "s", _RuntimeToken())          # token not minted by this runtime
    denied(k.dispatch(forged, "read_audit", {}), "unknown_identity")
    other_runtime_ctx = KernelRuntime().context_for("human")
    denied(k.dispatch(other_runtime_ctx, "read_audit", {}), "unknown_identity")
    denied(k.dispatch(k.runtime.context_for("nobody"), "get_authorization_profile", {}), "unknown_identity")
    assert all(e["agent_id"] for e in k.audit.events())


# ---------------------------------------------------------------- 39.3 capability and scope (I3, I17)
def test_ac06_permission_boundary_read_but_not_apply(kernel_root):
    k = K(kernel_root)
    assert k.dispatch(k.ctx_proposer, "read_workspace_file", {"path": "src/calc.py"}).allowed
    rid = make_request(k); approve(k, rid)
    before = (kernel_root / "workspace" / "src" / "calc.py").read_text()
    denied(k.dispatch(k.ctx_proposer, "apply_approved_request", {"request_id": rid}), "missing_permission")
    assert (kernel_root / "workspace" / "src" / "calc.py").read_text() == before


def test_ac07_resource_scope_boundary(kernel_root):
    k = K(kernel_root)
    k.tasks.add("t1", "x", "x")
    for path in ("other/file.py", "../escape.py", "state/STOP", "kernel/loop.py"):
        res = k.dispatch(k.ctx_proposer, "propose_patch", {"task_id": "t1", "files": {path: "x"}, "rationale": "r", "evidence": GOOD_EVIDENCE})
        assert res.authz.result == DENY and res.authz.reason in ("scope_violation", "unknown_resource", "policy_block"), (path, res.authz)
    # mixed: one in-scope file plus one out-of-scope file -> the whole call is denied
    denied(k.dispatch(k.ctx_proposer, "propose_patch", {"task_id": "t1", "files": {"src/a.py": "x", "other/b.py": "y"}, "rationale": "r", "evidence": GOOD_EVIDENCE}), "scope_violation")


def test_ac08_similar_capability_does_not_imply_another(kernel_root):
    k = K(kernel_root)
    prof = k.dispatch(k.ctx_proposer, "get_authorization_profile", {}).output
    perms = {c["permission"] for c in prof["capabilities"]}
    assert "PROPOSE_PATCH" in perms and "APPLY_PATCH" not in perms and "RUN_TESTS" not in perms
    denied(k.dispatch(k.ctx_proposer, "run_tests", {}), "missing_permission")
    denied(k.dispatch(k.ctx_proposer, "record_approval", {"request_id": "x", "phrase": "y"}), "missing_permission")


def test_i17_trust_counters_do_not_create_authority(kernel_root):
    k = K(kernel_root)
    for _ in range(5):
        make_request(K(kernel_root) if False else k) if False else None
    k._record(applied=100, escalations=50)   # a "high trust" record
    denied(k.dispatch(k.ctx_proposer, "read_audit", {}), "missing_permission")
    denied(k.dispatch(k.ctx_proposer, "run_tests", {}), "missing_permission")


# ---------------------------------------------------------------- 39.4 TWE isolation (I6, I18 architectural part)
def test_ac10_twe_access_only_through_functions_and_no_handles(kernel_root):
    k = K(kernel_root)
    rid = make_request(k)
    res = k.dispatch(k.ctx_proposer, "read_twe", {"twe_id": "twe/proposer"})
    assert res.allowed and isinstance(res.output, list) and res.output[-1]["id"] == rid
    text = json.dumps(res.output)
    assert "state/twe" not in text and ".jsonl" not in text and str(kernel_root) not in text
    # the proposer cannot read another principal's TWE
    denied(k.dispatch(k.ctx_proposer, "read_twe", {"twe_id": "twe/human"}), "scope_violation")


def test_ac11_workspace_permissions_do_not_grant_twe(kernel_root):
    text = (kernel_root / "permissions.toml").read_text()
    text = text.replace('  { permission = "TWE_READ",       scope = "twe/proposer" },\n  { permission = "TWE_APPEND",     scope = "twe/proposer" },\n', "")
    (kernel_root / "permissions.toml").write_text(text)
    k = K(kernel_root)
    assert k.dispatch(k.ctx_proposer, "read_workspace_tree", {}).allowed
    denied(k.dispatch(k.ctx_proposer, "read_twe", {"twe_id": "twe/proposer"}), "missing_permission")
    denied(k.dispatch(k.ctx_proposer, "report_blocker", {"twe_id": "twe/proposer", "task_id": "t", "blocker": {"nature": "n"}}), "missing_permission")


def test_agent_never_receives_storage_paths(kernel_root):
    k = K(kernel_root, [patch_call()])
    k.tasks.add("t1", "add mul", "add mul")
    k.propose()
    system, user = k.proposer.calls[0]
    for needle in ("state/", "approvals", "audit.jsonl", "police.jsonl", "permissions.toml", str(kernel_root)):
        assert needle not in system + user, needle


# ---------------------------------------------------------------- 39.5 request immutability and approval binding (I12, I13, I4)
def test_ac12_request_ids_unique(kernel_root):
    k = K(kernel_root)
    ids = {k.twe.append_request("twe/proposer", "proposer", "patch", "APPLY_PATCH", ["workspace/src/a.py"], {"n": i})["id"] for i in range(10000)}
    assert len(ids) == 10000


def test_ac13_submitted_request_is_immutable(kernel_root):
    k = K(kernel_root)
    rid = make_request(k)
    assert not hasattr(k.twe, "modify_entry") and not hasattr(k.twe, "delete_entry") and not hasattr(k.twe, "overwrite_entry")
    original = k.twe.get_request(rid)
    # direct modification of storage is detected: hashes no longer match and the chain fails
    p = kernel_root / "state" / "twe" / "proposer.jsonl"
    lines = p.read_text().splitlines()
    e = json.loads(lines[-1]); e["payload"]["files"]["src/calc.py"] = "def add(a, b):\n    return 42\n"
    lines[-1] = json.dumps(e, sort_keys=True); p.write_text("\n".join(lines) + "\n")
    tampered = k.twe.get_request(rid)
    assert tampered["hash"] != tampered["recomputed_hash"] and not k.twe.verify("twe/proposer")[0]
    approve(k, rid) if False else None
    denied(k.dispatch(k.ctx_human, "apply_approved_request", {"request_id": rid}), "hash_mismatch")
    assert original["files"] == GOOD_PATCH


def test_ac14_approval_bound_to_exact_request(kernel_root):
    k = K(kernel_root)
    rid_a = make_request(k)
    approve(k, rid_a)
    # substitute request B under A's approval record
    rid_b = k.twe.append_request("twe/proposer", "proposer", "patch", "APPLY_PATCH", ["workspace/src/calc.py"], {"files": BAD_PATCH, "rationale": "b", "evidence": GOOD_EVIDENCE}, task_id="t1")["id"]
    rec = kernel_root / "state" / "approvals" / "records"
    (rec / f"{rid_b}.json").write_text((rec / f"{rid_a}.json").read_text().replace(rid_a, rid_b))
    res = denied(k.dispatch(k.ctx_human, "apply_approved_request", {"request_id": rid_b}))
    assert res.authz.reason in ("hash_mismatch", "invalid_approval")
    assert "a - b" not in (kernel_root / "workspace" / "src" / "calc.py").read_text()


def test_ac15_narrow_approval_cannot_authorize_broader_scope(kernel_root):
    k = K(kernel_root)
    rid = make_request(k, files={"src/calc.py": GOOD_PATCH["src/calc.py"], "src/extra.py": "x = 1\n"})
    approve(k, rid)
    rec = kernel_root / "state" / "approvals" / "records" / f"{rid}.json"
    appr = json.loads(rec.read_text()); appr["scope"] = ["workspace/src/calc.py"]   # narrowed record (hash now stale)
    rec.write_text(json.dumps(appr))
    res = denied(k.dispatch(k.ctx_human, "apply_approved_request", {"request_id": rid}))
    assert res.authz.reason in ("invalid_approval", "approval_scope_exceeded")
    # a consistent narrow approval (re-hashed) is still rejected on scope
    from kernel.authz import canonical_hash
    appr.pop("record_hash", None); appr["record_hash"] = canonical_hash(appr); rec.write_text(json.dumps(appr))
    denied(k.dispatch(k.ctx_human, "apply_approved_request", {"request_id": rid}), "approval_scope_exceeded")
    assert not (kernel_root / "workspace" / "src" / "extra.py").exists()


def test_self_approval_is_denied(kernel_root):
    k = K(kernel_root)
    rid = make_request(k)
    text = (kernel_root / "permissions.toml").read_text().replace('  { permission = "TWE_APPEND",     scope = "twe/proposer" },\n',
            '  { permission = "TWE_APPEND",     scope = "twe/proposer" },\n  { permission = "APPROVAL_APPEND", scope = "approval/*" },\n')
    (kernel_root / "permissions.toml").write_text(text)
    k2 = K(kernel_root)
    denied(k2.dispatch(k2.ctx_proposer, "record_approval", {"request_id": rid, "phrase": k2.c.approval_phrase.format(request_id=rid)}), "policy_block")


def test_rejected_request_cannot_be_applied_and_phrase_must_be_exact(kernel_root):
    k = K(kernel_root)
    rid = make_request(k)
    denied(k.approve(rid, f"i approve {rid}"), "policy_block")
    assert k.approve(rid, k.c.rejection_phrase.format(request_id=rid)).allowed
    denied(k.dispatch(k.ctx_human, "apply_approved_request", {"request_id": rid}), "rejected")


def test_expired_approval_is_denied(kernel_root):
    k = K(kernel_root)
    rid = make_request(k); approve(k, rid)
    rec = kernel_root / "state" / "approvals" / "records" / f"{rid}.json"
    appr = json.loads(rec.read_text()); appr["ts"] = time.time() - 10 * 24 * 3600
    from kernel.authz import canonical_hash
    appr.pop("record_hash"); appr["record_hash"] = canonical_hash(appr); rec.write_text(json.dumps(appr))
    denied(k.dispatch(k.ctx_human, "apply_approved_request", {"request_id": rid}), "expired_approval")


# ---------------------------------------------------------------- 39.6 evidence (I5)
def test_ac16_missing_evidence_denies_before_execution(kernel_root):
    k = K(kernel_root)
    k.tasks.add("t1", "x", "x")
    n = len(k.twe.read("twe/proposer"))
    denied(k.dispatch(k.ctx_proposer, "propose_patch", {"task_id": "t1", "files": GOOD_PATCH, "rationale": "r"}), "missing_evidence")
    assert len(k.twe.read("twe/proposer")) == n and k.pending_requests() == []


def test_ac17_unverified_information_cannot_satisfy_evidence(kernel_root):
    k = K(kernel_root)
    k.tasks.add("t1", "x", "x")
    only_hyp = {"verified_facts": [], "observed": [], "sourced": [], "derived": [], "hypotheses": ["I am confident add works"], "unknown": []}
    denied(k.dispatch(k.ctx_proposer, "propose_patch", {"task_id": "t1", "files": GOOD_PATCH, "rationale": "trust me", "confidence": 0.99, "evidence": only_hyp}), "missing_evidence")
    unsourced = dict(GOOD_EVIDENCE, verified_facts=[], observed=[], derived=[], sourced=["the docs say so"])
    denied(k.dispatch(k.ctx_proposer, "propose_patch", {"task_id": "t1", "files": GOOD_PATCH, "rationale": "r", "evidence": unsourced}), "missing_evidence")
    assert k.pending_requests() == []


# ---------------------------------------------------------------- 39.7 audit (I7, I8)
def test_ac18_ac19_every_request_audited_with_identity(kernel_root):
    k = K(kernel_root)
    k.tasks.add("t1", "x", "x")
    start = len(list(k.audit.events()))
    calls = [
        (k.ctx_proposer, "get_authorization_profile", {}),                                                  # allowed
        (k.ctx_proposer, "read_audit", {}),                                                                 # missing permission
        (k.ctx_proposer, "nope", {}),                                                                       # unknown function
        (k.ctx_proposer, "propose_patch", {"task_id": "t1", "files": {"../x": "y"}, "evidence": GOOD_EVIDENCE}),  # out of scope
        (k.ctx_proposer, "propose_patch", {"task_id": "t1", "files": GOOD_PATCH, "rationale": "r"}),        # missing evidence
        (k.ctx_human, "apply_approved_request", {"request_id": "req-none"}),                                # unknown request
        (None, "read_audit", {}),                                                                           # no identity
    ]
    for ctx, f, a in calls:
        k.dispatch(ctx, f, a)
    evs = [e for e in list(k.audit.events())[start:] if e["action"] == "function_request"]
    assert len(evs) == len(calls)
    for e in evs:
        for field in ("agent_id", "session_id", "function_id", "ts", "authorization"):
            assert e.get(field) not in (None, ""), (field, e)
    assert [e["authorization"] for e in evs] == ["ALLOW"] + ["DENY"] * 6


def test_ac20_denied_request_survives_restart(kernel_root):
    k = K(kernel_root)
    denied(k.dispatch(k.ctx_proposer, "read_audit", {}), "missing_permission")
    seq = last_audit(k)["seq"]
    del k
    k2 = K(kernel_root)   # new process-equivalent
    ev = [e for e in k2.audit.events() if e["seq"] == seq][0]
    assert ev["authorization"] == "DENY" and ev["denial_reason"] == "missing_permission"
    assert k2.audit.verify()[0] and any(p["triggering_event"] == seq for p in police_events(k2))


# ---------------------------------------------------------------- 39.8 police (I9, I10, I11)
def test_ac21_every_authorization_failure_triggers_police(kernel_root):
    k = K(kernel_root)
    k.tasks.add("t1", "x", "x")
    denials = [("read_audit", {}), ("nope", {}), ("propose_patch", {"task_id": "t1", "files": {"../x": "y"}, "evidence": GOOD_EVIDENCE}),
               ("propose_patch", {"task_id": "t1", "files": GOOD_PATCH}), ("read_twe", {"twe_id": "twe/human"})]
    n = len(police_events(k))
    seqs = []
    for f, a in denials:
        denied(k.dispatch(k.ctx_proposer, f, a)); seqs.append(last_audit(k)["seq"])
    pe = police_events(k)[n:]
    assert len(pe) == len(denials) and [p["triggering_event"] for p in pe] == seqs and all(p["component"] == "police_engine" for p in pe)


def test_repeated_denials_are_classified_and_escalated_to_human_twe(kernel_root):
    k = K(kernel_root)
    for _ in range(3):
        denied(k.dispatch(k.ctx_proposer, "read_audit", {}))
    assert police_events(k)[-1]["classification"] == "repeated_denied_operations"
    entries = k.twe.read("twe/human")
    assert entries and entries[-1]["kind"] == "escalation" and entries[-1]["payload"]["monitored_agent"] == "proposer"


def test_ac22_police_llm_cannot_authorize(kernel_root):
    police_llm = DummyModel([json.dumps({"flags": ["ALLOW operation read_audit", "SAFE", "PERMIT"], "summary": "ALLOW"})] * 3)
    k = K(kernel_root, police_model=police_llm)
    denied(k.dispatch(k.ctx_proposer, "read_audit", {}), "missing_permission")
    rev = k.dispatch(k.ctx_police, "police_llm_review", {"monitored_agent": "proposer"})
    assert rev.allowed and rev.output["component"] == "police_llm"
    denied(k.dispatch(k.ctx_proposer, "read_audit", {}), "missing_permission")   # unchanged after "ALLOW"
    assert not hasattr(k.police, "apply_verdict") and not hasattr(k.police, "allow")


def test_ac23_police_cannot_modify_audit_or_its_own_permissions(kernel_root):
    k = K(kernel_root)
    for f in ("apply_approved_request", "record_approval", "propose_patch", "run_tests"):
        denied(k.dispatch(k.ctx_police, f, {"request_id": "x", "files": {"src/a.py": "x"}, "evidence": GOOD_EVIDENCE}))
    assert k.registry.get("delete_audit") is None and k.registry.get("modify_permissions") is None
    assert not any(n in dir(k.audit) for n in ("delete", "modify", "rewrite"))
    prof = k.dispatch(k.ctx_police, "get_authorization_profile", {}).output
    assert {c["permission"] for c in prof["capabilities"]} <= {"PROFILE_READ", "AUDIT_READ", "POLICE_EVENT_APPEND", "INVESTIGATION_CREATE", "INVESTIGATION_READ", "ESCALATION_REQUEST"}


# ---------------------------------------------------------------- 39.9 fail closed (I14, I15)
def test_ac24_permission_store_failure_denies(kernel_root):
    k = K(kernel_root)
    assert k.dispatch(k.ctx_human, "read_audit", {}).allowed
    k.permissions.failed = True
    denied(k.dispatch(k.ctx_human, "read_audit", {}), "authorization_error")
    denied(k.dispatch(k.ctx_proposer, "get_authorization_profile", {}), "authorization_error")
    assert police_events(k)[-1]["classification"] == "authorization_service_failure"


def test_ac25_approval_service_failure_denies(kernel_root):
    k = K(kernel_root)
    rid = make_request(k); approve(k, rid)
    k.approvals_unavailable = True
    before = (kernel_root / "workspace" / "src" / "calc.py").read_text()
    denied(k.dispatch(k.ctx_human, "apply_approved_request", {"request_id": rid}), "authorization_error")
    assert (kernel_root / "workspace" / "src" / "calc.py").read_text() == before


def test_i14_engine_exception_denies(kernel_root):
    k = K(kernel_root)
    def boom(a):
        raise RuntimeError("resource resolver crashed")
    k.registry.register(FunctionSpec("weird", "PROFILE_READ", boom, lambda ctx, a: "ran"))
    denied(k.dispatch(k.ctx_proposer, "weird", {}), "authorization_error")


# ---------------------------------------------------------------- 39.11 audit integrity (I11)
def test_ac28_historical_modification_detectable(kernel_root):
    k = K(kernel_root)
    k.dispatch(k.ctx_proposer, "get_authorization_profile", {})
    p = kernel_root / "state" / "audit.jsonl"
    lines = p.read_text().splitlines()
    e = json.loads(lines[-1]); e["authorization"] = "DENY" if e["authorization"] == "ALLOW" else "ALLOW"
    lines[-1] = json.dumps(e, sort_keys=True, separators=(",", ":")); p.write_text("\n".join(lines) + "\n")
    ok, msg = AuditLedger(p, k.c.sha256).verify()
    assert not ok and "hash mismatch" in msg
    lines = p.read_text().splitlines(); del lines[1]; p.write_text("\n".join(lines) + "\n")
    assert not AuditLedger(p, k.c.sha256).verify()[0]


def test_ac29_audit_and_police_chains_survive_restart(kernel_root):
    k = K(kernel_root)
    denied(k.dispatch(k.ctx_proposer, "read_audit", {}))
    n_a, n_p = len(list(k.audit.events())), len(police_events(k))
    del k
    k2 = K(kernel_root)
    denied(k2.dispatch(k2.ctx_proposer, "read_audit", {}))
    assert k2.audit.verify()[0] and k2.police.verify()[0]
    assert len(list(k2.audit.events())) > n_a and len(police_events(k2)) == n_p + 1
    assert police_events(k2)[-1]["prev_hash"] == police_events(k2)[-2]["hash"]


# ---------------------------------------------------------------- end-to-end through the model interface
def test_model_cannot_apply_or_approve_through_calls(kernel_root):
    k = K(kernel_root, [patch_call()])
    k.tasks.add("t1", "add mul", "add mul")
    res = k.propose(); rid = res.output["request_id"]
    k2 = K(kernel_root, [call_json("record_approval", request_id=rid, phrase=k.c.approval_phrase.format(request_id=rid)),
                         call_json("apply_approved_request", request_id=rid)])
    k2.tasks.add("t2", "x", "x"); k2.tasks.add("t3", "x", "x")
    denied(k2.propose(), "missing_permission")
    denied(k2.propose(), "missing_permission")
    assert "mul" not in (kernel_root / "workspace" / "src" / "calc.py").read_text()


def test_full_cycle_propose_approve_apply_via_functions(kernel_root):
    k = K(kernel_root, [patch_call()])
    k.tasks.add("t1", "add mul", "add mul")
    res = k.propose(); assert res.allowed
    rid = res.output["request_id"]
    assert rid in k.pending_requests() and k.tasks.counts()["active"] == 1
    approve(k, rid)
    out = k.apply(rid); assert out.allowed and out.output["applied"]
    assert "mul" in (kernel_root / "workspace" / "src" / "calc.py").read_text() and k.tasks.counts()["done"] == 1
    assert k.audit.verify()[0] and k.twe.verify("twe/proposer")[0]
    kinds = [e["kind"] for e in k.twe.read("twe/proposer")]
    assert kinds == ["request", "approval_notice", "disposition"]
