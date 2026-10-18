"""Operational safety-property tests for kernel v2.0 (halts, checkpoints, rollback, escalation,
incidents, refresher, evidence rendering, constitution self-protection). Security-boundary tests
are in test_security.py."""
import json
import time
from pathlib import Path

import pytest

from kernel import Halted, KernelError
from kernel.audit import AuditLedger
from kernel.constitution import load_constitution
from kernel.loop import Kernel, Layout
from kernel.model import DummyModel
from kernel.policy import evaluate
from kernel.model import Proposal

from conftest import BAD_PATCH, GOOD_EVIDENCE, GOOD_PATCH, blocker_call, call_json, patch_call


def K(root: Path, responses=None) -> Kernel:
    return Kernel(Layout.at(root), proposer=DummyModel(responses or []), monitor=DummyModel([]), install_signal_handlers=False)


def approve(k, rid):
    assert k.approve(rid, k.c.approval_phrase.format(request_id=rid)).allowed


# ------------------------------------------------------------------ audit / constitution
def test_audit_redacts_secrets(tmp_path):
    led = AuditLedger(tmp_path / "audit.jsonl", "abc")
    led.append("kernel", "x", "t", "ok", api_key="sk-live-123", nested={"password": "p"})
    text = (tmp_path / "audit.jsonl").read_text()
    assert "sk-live-123" not in text and "[REDACTED]" in text


def test_constitution_refuses_unsupported_autonomy_and_missing_self_protection(kernel_root):
    c = (kernel_root / "constitution.toml").read_text()
    (kernel_root / "constitution.toml").write_text(c.replace("level = 1", "level = 2"))
    with pytest.raises(KernelError):
        load_constitution(kernel_root / "constitution.toml")
    (kernel_root / "constitution.toml").write_text(c.replace('"kernel/**",', ""))
    with pytest.raises(KernelError):
        load_constitution(kernel_root / "constitution.toml")


def test_constitution_and_permissions_changes_are_audited(kernel_root):
    K(kernel_root)
    for f, old, new in (("constitution.toml", "max_patch_files = 12", "max_patch_files = 13"), ("permissions.toml", 'version = "0.1.0"', 'version = "0.1.1"')):
        p = kernel_root / f; p.write_text(p.read_text().replace(old, new))
    k = K(kernel_root)
    actions = [e["action"] for e in k.audit.events()]
    assert "constitution_changed" in actions and "permissions_changed" in actions


def test_policy_blocks_kernel_constitution_state_and_secrets(kernel_root):
    c = load_constitution(kernel_root / "constitution.toml")
    for path in ("kernel/loop.py", "constitution.toml", "state/STOP", "../outside.py", "/etc/passwd"):
        assert evaluate(c, Proposal(files={path: "x"})).blocked, path
    assert evaluate(c, Proposal(files={"src/a.py": "api_key = 'sk-123'"})).blocked


# ------------------------------------------------------------------ halts
def test_stop_file_halts_before_any_model_call(kernel_root):
    k = K(kernel_root, [patch_call()])
    k.tasks.add("t1", "add mul", "add mul")
    (kernel_root / "state" / "STOP").write_text("halt\n")
    with pytest.raises(Halted):
        k.propose()
    assert k.proposer.calls == []


def test_halt_denies_dispatch_and_is_audited(kernel_root):
    k = K(kernel_root)
    k.halt.request_stop("drill")
    res = k.dispatch(k.ctx_proposer, "get_authorization_profile", {})
    assert res.authz.result == "DENY" and res.authz.reason == "halted"


def test_freeze_blocks_apply_but_not_proposals(kernel_root):
    k = K(kernel_root, [patch_call()])
    k.tasks.add("t1", "add mul", "add mul")
    (kernel_root / "state" / "FREEZE").write_text("x")
    res = k.propose(); assert res.allowed
    approve(k, res.output["request_id"])
    out = k.apply(res.output["request_id"])
    assert out.authz.result == "DENY" and out.authz.reason == "halted"


def test_resume_requires_exact_phrase_and_budget_breaker_persists(kernel_root):
    k = K(kernel_root)
    k.halt.set_limit("model_calls", 1); k.halt.count("model_calls")
    with pytest.raises(Halted):
        k.halt.count("model_calls")
    assert (kernel_root / "state" / "STOP").exists()
    assert not k.halt.resume("i resume the kernel", k.c.resume_phrase) and k.halt.stopped
    assert k.halt.resume(k.c.resume_phrase, k.c.resume_phrase) and not k.halt.stopped


# ------------------------------------------------------------------ apply, rollback, incidents
def test_failed_tests_roll_back_and_open_incident(kernel_root):
    k = K(kernel_root, [patch_call(files=BAD_PATCH)])
    k.tasks.add("t1", "break add", "change add")
    rid = k.propose().output["request_id"]; approve(k, rid)
    out = k.apply(rid)
    assert out.allowed and out.output["applied"] is False
    assert "a + b" in (kernel_root / "workspace" / "src" / "calc.py").read_text()
    incidents = list((kernel_root / "state" / "incidents").glob("inc-*rollback_after_tests_failed.md"))
    assert len(incidents) == 1 and "9. Changes that could reduce" in incidents[0].read_text()
    k.record_finding(incidents[0].stem, "reasonable", "task omitted the test contract")
    with pytest.raises(KernelError):
        k.record_finding(incidents[0].stem, "reasonable", "again")
    labels = [c.label for c in k.checkpoints.list()]
    assert any(l.startswith("before-") for l in labels) and any(l.startswith("pre-restore") for l in labels)


def test_block_on_kernel_path_opens_incident_and_is_denied(kernel_root):
    k = K(kernel_root, [patch_call(files={"kernel/loop.py": "x = 1"})])
    k.tasks.add("t1", "x", "x")
    res = k.propose()
    assert res.authz.result == "DENY"
    assert list((kernel_root / "state" / "incidents").glob("inc-*block_self_modification.md")) or res.authz.reason == "scope_violation"


def test_protected_test_change_and_hypotheses_are_escalated_in_packet(kernel_root):
    fewer = {"tests/test_calc.py": "import sys\n"}
    ev = dict(GOOD_EVIDENCE, hypotheses=["callers never pass negatives"])
    k = K(kernel_root, [patch_call(files=fewer, evidence=ev)])
    k.tasks.add("t1", "tidy tests", "tidy")
    res = k.propose(); assert res.allowed
    assert res.output["verdict"] == "ESCALATE"
    assert {"protected_test_change", "test_count_decreased", "depends_on_hypotheses"} <= set(res.output["flags"])
    packet = k.packet_text(res.output["request_id"])
    assert "HIGH RISK" in packet and "callers never pass negatives" in packet and "Request hash" in packet
    for section in ("Verified facts", "Directly observed", "From an identifiable source", "Derived from verified premises", "Hypotheses (unverified)", "Unknown or unavailable"):
        assert section in packet


# ------------------------------------------------------------------ escalation / blockers
def test_escalation_pauses_task_writes_blocker_and_twe_entry(kernel_root):
    k = K(kernel_root, [blocker_call()])
    k.tasks.add("t1", "add mul", "add mul")
    before = (kernel_root / "workspace" / "src" / "calc.py").read_text()
    res = k.propose(); assert res.allowed
    assert k.tasks.counts()["blocked"] == 1 and k.pending_requests() == []
    blocker = (kernel_root / "state" / "blockers" / "t1.md").read_text()
    for section in ("Nature of the problem", "Input needed", "Category: insufficient_information", "Verified facts", "Courses of action considered"):
        assert section in blocker
    assert (kernel_root / "workspace" / "src" / "calc.py").read_text() == before
    assert k.twe.read("twe/proposer")[-1]["kind"] == "blocker"


def test_blocked_task_does_not_prevent_next_task_and_unblock_shows_guidance(kernel_root):
    k = K(kernel_root, [blocker_call(), patch_call(), patch_call()])
    k.tasks.add("t1", "add mul", "add mul", priority=1); k.tasks.add("t2", "add mul", "add mul", priority=2)
    k.propose()                                     # t1 blocked
    res = k.propose(); assert res.allowed           # t2 proceeds
    assert k.tasks.counts()["blocked"] == 1 and k.tasks.counts()["active"] == 1
    k.unblock("t1", "leave test_calc unchanged; only add mul")
    assert k.tasks.counts()["queue"] == 1
    k.propose()
    assert "GUIDANCE: leave test_calc unchanged" in k.proposer.calls[-1][1]


def test_misleading_directive_report_opens_incident(kernel_root):
    k = K(kernel_root, [blocker_call(category="misleading_directive", nature="task says divide() exists; it does not")])
    k.tasks.add("t1", "fix divide", "fix divide()")
    assert k.propose().allowed
    assert list((kernel_root / "state" / "incidents").glob("inc-*directive_defect_reported.md")) and k.tasks.counts()["blocked"] == 1


def test_legacy_proposal_shape_is_mapped_to_functions(kernel_root):
    legacy = json.dumps({"status": "proposal", "rationale": "r", "files": GOOD_PATCH, "evidence": GOOD_EVIDENCE})
    esc = json.dumps({"status": "escalate", "blocker": {"category": "other", "nature": "n"}})
    k = K(kernel_root, [legacy, esc])
    k.tasks.add("t1", "add mul", "add mul"); k.tasks.add("t2", "x", "x")
    assert k.propose().output["request_id"].startswith("req-")
    assert k.propose().output["task_state"] == "blocked"


def test_abstain_parks_task(kernel_root):
    k = K(kernel_root, [call_json("abstain", rationale="outside competence")])
    k.tasks.add("t1", "x", "x")
    assert k.propose().allowed and k.tasks.counts()["parked"] == 1


def test_attempt_limit_parks_task(kernel_root):
    k = K(kernel_root, [patch_call(files={"kernel/x": "no"})] * 5)
    k.tasks.add("t1", "x", "x")
    for _ in range(4):
        k.propose()
    assert k.tasks.counts()["parked"] == 1


# ------------------------------------------------------------------ refresher and prompt content
def test_refresher_inserted_after_configured_activity(kernel_root):
    c = (kernel_root / "constitution.toml").read_text().replace("refresher_every_model_calls = 20", "refresher_every_model_calls = 2")
    (kernel_root / "constitution.toml").write_text(c)
    k = K(kernel_root, [call_json("abstain", rationale="r")] * 4)
    for i in range(4):
        k.tasks.add(f"t{i}", "x", "x")
    for _ in range(3):
        k.propose()
    systems = [s for s, _ in k.proposer.calls]
    assert "REFRESHER" not in systems[0] and "REFRESHER" in systems[2]


def test_prompt_contains_profile_categories_standard_and_no_secrets(kernel_root, monkeypatch):
    monkeypatch.setenv("SEED_PROPOSER_API_KEY", "sk-supersecret")
    k = K(kernel_root, [patch_call()])
    k.tasks.add("t1", "add mul", "add mul")
    k.propose()
    system, user = k.proposer.calls[0]
    for needle in ("AUTHORIZATION PROFILE", "PROPOSE_PATCH", "twe/proposer", "Hard constraints", "Escalation conditions",
                   "HIGH-STAKES CONSEQUENCE CLASSES", "EVIDENTIARY STANDARD", "PRECEDENCE", "imprecise or ambiguous (report before proceeding)",
                   "identity is attached by the runtime"):
        assert needle in system, needle
    assert "sk-supersecret" not in system + user


def test_checkpoint_restore_roundtrip(kernel_root):
    k = K(kernel_root)
    cp = k.checkpoints.take("manual")
    (kernel_root / "workspace" / "src" / "calc.py").write_text("garbage")
    k.checkpoints.restore(cp.id)
    assert "a + b" in (kernel_root / "workspace" / "src" / "calc.py").read_text() and k.checkpoints.verify(cp.id)


def test_workspace_dir_outside_kernel_root_and_refusals(kernel_root, tmp_path):
    """v2.6: [paths] workspace_dir may point outside the kernel folder; overlapping the kernel or its state is refused."""
    import re
    from kernel import KernelError
    from kernel.loop import Kernel, Layout
    from kernel.model import DummyModel
    ext = tmp_path.parent / (tmp_path.name + "_platform"); (ext / "tests").mkdir(parents=True); (ext / "src").mkdir()   # a sibling folder
    (ext / "src" / "__init__.py").write_text(""); (ext / "tests" / "test_x.py").write_text("def test_x():\n    assert True\n")
    c = kernel_root / "constitution.toml"
    def set_ws(value):
        c.write_text(re.sub(r'^workspace_dir = .*$', f'workspace_dir = "{value}"', c.read_text(encoding="utf-8"), flags=re.M), encoding="utf-8")
    set_ws(f"../{ext.name}")
    k = Kernel(Layout.at(kernel_root), proposer=DummyModel([]), monitor=DummyModel([]), install_signal_handlers=False)
    assert k.layout.workspace == ext.resolve() and "tests/test_x.py" in k.ws.tree()
    for bad in (".", "state", "state/x", "kernel", "../.."):
        set_ws(bad)
        with pytest.raises(KernelError):
            Kernel(Layout.at(kernel_root), proposer=DummyModel([]), monitor=DummyModel([]), install_signal_handlers=False)
