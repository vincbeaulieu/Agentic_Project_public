"""Kernel v2.0: function-call interface, default-deny authorization, TWE service, police (rule R04).

Execution path for every agent request:

    model output -> parsed FunctionCall -> Kernel.dispatch(ctx, function, args)
        -> AuthorizationEngine (identity, function, resources, capability, scope, halt,
           request state, evidence, approval, policy)            [deterministic; fail closed]
        -> DENY: audit event -> PoliceEngine.inspect
        -> ALLOW: handler executes -> audit event (output hash)

The proposer model receives its authorization profile in every prompt and can call only the
functions registered in `_register_functions`. It never receives a path, file handle or
storage location; TWE, approval, audit, police and permission storage are reached only
through those functions, each requiring an explicit capability. Nothing in this file consults
a model for an authorization decision.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from . import Halted, KernelError
from .audit import AuditLedger
from .authz import (ALLOW, DENY, AgentContext, AuthorizationEngine, AuthzResult, FunctionRegistry, FunctionSpec,
                    KernelRuntime, PermissionStore, canonical_hash)
from .checkpoint import CheckpointStore
from .constitution import Constitution, load_constitution
from .halt import HaltController
from .model import PROPOSAL_SCHEMA_HINT, ChatModel, Proposal, _extract_json, build_model, parse_evidence
from .police import PoliceEngine
from .policy import evaluate
from .sandbox import RunResult, Workspace, run_tests
from .tasks import Task, TaskStore
from .twe import TWEService

KERNEL = "kernel"

FUNCTION_CALL_HINT = """Respond with ONE JSON object describing ONE kernel function call and nothing else:
{"call": "<function id from your authorization profile>", "args": { ... }}

Functions available to a proposer (each call is authorized by the kernel; calling is a request, not authorization):
  propose_patch   args: {"task_id", "files": {"relative/path": "full content"}, "rationale", "evidence": {...six categories...},
                         "unresolved": [], "considered_actions": [], "risk_self_report": "low|medium|high", "confidence": 0.0}
                  -> creates an immutable request in your TWE and an approval packet for the human. Requires the evidence block.
  report_blocker  args: {"twe_id", "task_id", "blocker": {"category", "nature", "constraint", "input_needed"}, "evidence": {...},
                         "unresolved": [], "considered_actions": [], "rationale"}
                  -> pauses the task, records the blocker, changes nothing. Use for escalation conditions.
  abstain         args: {"twe_id", "task_id", "rationale"}   -> the task is parked for a human decision.
  read_twe        args: {"twe_id"}                            -> entries of a TWE you may read.
  read_workspace_file args: {"path"}                          -> contents of a workspace file you may read.
  get_authorization_profile args: {}                          -> your current capabilities and permitted functions.
Do not include agent_id or any identity field: identity is attached by the runtime. Your own TWE id is in the profile.
""" + PROPOSAL_SCHEMA_HINT.replace("Respond with ONE JSON object and nothing else:", "Evidence block and fields (used inside propose_patch / report_blocker args):")

DEFAULT_REFRESHER = """REFRESHER (inserted by the kernel after a configured amount of activity).
1. Recognizing a condition is separate from resolving it. When a condition exceeds your authority or the
   review requirements, escalate (report_blocker); do not repair it yourself.
2. Known failure patterns to check your own output against: modifying or weakening tests to make them pass;
   proceeding on an assumption that was not verified; treating a consequential change as routine because it is
   technically small; working around a conflicting instruction instead of reporting the conflict; omitting an
   observed anomaly from the report; probing functions outside your authorization profile.
3. Appropriate escalation example: "Existing test test_x fails before my change; the task does not mention it.
   Escalating: input needed on whether to fix test_x or treat it as out of scope." Nothing is changed.
4. Reporting a condition promptly and accurately is the expected behaviour and is recorded as such.
5. An imprecise directive is reported before proceeding. A directive that appears erroneous or misleading
   is reported and the task stays paused until it is corrected; it is not worked around.
6. Evidence: a premise is either verified, observed, sourced (with the source named), or derived from listed
   verified premises. Anything else is a hypothesis or unknown and is labelled as such. A required premise
   that cannot be verified is an evidentiary gap to report, not a value to assume.
7. Authority: consult your authorization profile before a call. A denied call is recorded and reviewed by the
   police subsystem; it is not a failure of judgment by itself, but repeated attempts at unavailable functions are.
"""

INCIDENT_TEMPLATE = """# Incident {incident_id}

- Kind: {kind}
- Opened: {stamp} (automatically, by the kernel)
- Task: {task}
- Request: {request}
- Constitution: v{version} sha256 {sha}
- Audit sequence at opening: {seq}

## Automatically recorded facts
{facts}

## Analysis (to be completed by the human; see D3 §7.7)
1. What happened:
2. What conditions and events led to it:
3. Which assumptions, directives, environmental conditions, dependencies or interactions contributed:
4. Whether the agent had sufficient information and authority to identify and prevent the situation:
5. Whether an alternative decision was reasonably available at the time:
6. Whether instructions, policies or constraints were erroneous, misleading, incomplete, ambiguous, inconsistent or conflicting:
7. Whether the applicable procedures and escalation requirements were followed:
8. Whether the incident was detected and reported promptly:
9. Changes that could reduce the probability or impact of recurrence (instructions, permissions, kernel
   constraints, validation, monitoring, documentation, task decomposition, escalation, environment,
   dependencies, testing, human review, training/evaluation):

## Finding
- Judgment: (unrecorded; set with `python -m kernel finding {incident_id} <reasonable|judgment_failure|undetermined> "note"`)
"""


@dataclass
class Layout:
    root: Path
    constitution: Path
    permissions: Path
    state: Path
    workspace: Path

    @classmethod
    def at(cls, root: Path) -> "Layout":
        root = root.resolve()
        return cls(root, root / "constitution.toml", root / "permissions.toml", root / "state", root / "workspace")


@dataclass
class DispatchResult:
    authz: AuthzResult
    output: Any = None
    audit_seq: int = 0
    error: str = ""

    @property
    def allowed(self) -> bool:
        return self.authz.allowed and not self.error


class Kernel:
    def __init__(self, layout: Layout, *, proposer: ChatModel | None = None, monitor: ChatModel | None = None,
                 police_model: ChatModel | None = None, assistant: ChatModel | None = None,
                 install_signal_handlers: bool = True) -> None:
        self.c: Constitution = load_constitution(layout.constitution)
        layout = self._resolve_workspace(layout)
        self.layout = layout
        layout.state.mkdir(parents=True, exist_ok=True)
        self.audit = AuditLedger(layout.state / "audit.jsonl", self.c.sha256)
        self.halt = HaltController(layout.state, install_signal_handlers=install_signal_handlers)
        self.checkpoints = CheckpointStore(layout.state, layout.workspace)
        self.ws = Workspace(layout.workspace)
        self.tasks = TaskStore(layout.state)
        self.twe = TWEService(layout.state)
        self.permissions = PermissionStore(layout.permissions)
        self.runtime = KernelRuntime()
        self.registry = FunctionRegistry()
        self.approvals_dir = layout.state / "approvals"
        (self.approvals_dir / "pending").mkdir(parents=True, exist_ok=True)
        (self.approvals_dir / "records").mkdir(parents=True, exist_ok=True)
        self.approvals_unavailable = False   # fault injection for AC-25
        self.blockers_dir = layout.state / str(self.c.data.get("escalation", {}).get("blocker_dir", "blockers"))
        self.incidents_dir = layout.state / str(self.c.data.get("incidents", {}).get("incident_dir", "incidents"))
        for d in (self.blockers_dir, self.incidents_dir, layout.state / "training"):
            d.mkdir(parents=True, exist_ok=True)
        models = self.c.section("models")
        allow_remote = bool(models.get("allow_remote_endpoints", False))
        self.proposer = proposer or build_model(models["proposer"], allow_remote=allow_remote)
        self.monitor = monitor or build_model(models["monitor"], allow_remote=allow_remote)
        if police_model is None and "police" in models and str(models["police"].get("provider", "dummy")) != "dummy":
            police_model = build_model(models["police"], allow_remote=allow_remote)
        self.police_model = police_model
        # Task-drafting assistant (v2.5): no authority; [models.assistant] provider "proposer" reuses the proposer model,
        # "dummy" disables the assistant, anything else builds a separate model.
        acfg = models.get("assistant") or {}
        if assistant is not None:
            self.assistant_model = assistant
        elif str(acfg.get("provider", "proposer")) in ("proposer", ""):
            self.assistant_model = self.proposer
        elif str(acfg.get("provider")) == "dummy":
            self.assistant_model = None
        else:
            self.assistant_model = build_model(acfg, allow_remote=allow_remote)
        self.halt.set_limit("model_calls", self.c.budget("max_model_calls_per_cycle"))
        self.halt.set_limit("cycles_today", self.c.budget("max_cycles_per_day"))
        self._register_functions()
        self.engine = AuthorizationEngine(self.permissions, self.registry, self.runtime, request_state=self._request_state,
                                          approval_state=self._approval_state, evidence_check=self._evidence_ok,
                                          policy_check=self._policy_ok, halted=self._halted_reason)
        self.police = PoliceEngine(layout.state, escalate=self._police_escalate)
        self.ctx_proposer = self.runtime.context_for("proposer")
        self.ctx_human = self.runtime.context_for("human")
        self.ctx_police = self.runtime.context_for("police")
        self._record_hashes_seen()
        ok, msg = self.audit.verify()
        if not ok:
            self._open_incident("audit_chain_inconsistent", task="-", request="-", facts=[msg])

    # ================================================================ registry
    def _resolve_workspace(self, layout: Layout) -> Layout:
        """[paths] workspace_dir (v2.6): the governed workspace may live outside the kernel folder (e.g. the platform).
        Refused: the kernel root itself, anything inside state/ or kernel/, and any folder that contains the kernel root."""
        wd = str(self.c.section("paths").get("workspace_dir", "") or "").strip()
        if not wd:
            return layout
        target = (layout.root / wd).resolve()
        root = layout.root.resolve()
        forbidden = [root, (root / "state").resolve(), (root / "kernel").resolve()]
        if target in forbidden or any(f in target.parents for f in forbidden[1:]) or target in root.parents:
            raise KernelError(f"workspace_dir {wd!r} resolves to {target}, which would overlap the kernel or its state")
        return replace(layout, workspace=target)

    def _register_functions(self) -> None:
        R = self.registry.register
        R(FunctionSpec("get_authorization_profile", "PROFILE_READ", lambda a: ["self"], self._f_profile,
                       description="machine-readable capabilities, scopes and permitted functions of the caller"))
        R(FunctionSpec("read_workspace_tree", "WORKSPACE_READ", lambda a: ["workspace"], self._f_tree))
        R(FunctionSpec("read_workspace_file", "WORKSPACE_READ", lambda a: [_wsres(a.get("path"))], self._f_read_file))
        R(FunctionSpec("read_twe", "TWE_READ", lambda a: [str(a.get("twe_id", ""))], self._f_read_twe))
        R(FunctionSpec("propose_patch", "PROPOSE_PATCH", lambda a: [_wsres(p) for p in (a.get("files") or {})], self._f_propose_patch,
                       consequential=False, requires_evidence=True, description="create an immutable patch request + approval packet"))
        R(FunctionSpec("request_action", "TWE_APPEND", lambda a: [str(a.get("twe_id", ""))], self._f_request_action,
                       requires_evidence=True, description="record a request for an action that the kernel cannot execute at this stage"))
        R(FunctionSpec("report_blocker", "TWE_APPEND", lambda a: [str(a.get("twe_id", ""))], self._f_report_blocker,
                       description="escalate: pause the task, record the blocker, change nothing"))
        R(FunctionSpec("abstain", "TWE_APPEND", lambda a: [str(a.get("twe_id", ""))], self._f_abstain))
        R(FunctionSpec("record_approval", "APPROVAL_APPEND", lambda a: [f"approval/{a.get('request_id', '')}"], self._f_record_approval,
                       description="human: bind an approval or rejection to the exact request hash"))
        R(FunctionSpec("apply_approved_request", "APPLY_PATCH", self._resources_of_request, self._f_apply, consequential=True,
                       requires_evidence=True, requires_approval=True, description="human: checkpoint, write, test, checkpoint/rollback"))
        R(FunctionSpec("run_tests", "RUN_TESTS", lambda a: ["workspace"], lambda ctx, a: run_tests(self.c, self.ws).__dict__))
        R(FunctionSpec("read_audit", "AUDIT_READ", lambda a: ["audit/ledger"], lambda ctx, a: list(self.audit.events())[-int(a.get("limit", 100)):]))
        R(FunctionSpec("read_police", "POLICE_READ", lambda a: ["police/log"], lambda ctx, a: self.police.events()[-int(a.get("limit", 100)):]))
        R(FunctionSpec("police_llm_review", "POLICE_EVENT_APPEND", lambda a: ["police/log"], self._f_police_review,
                       description="police service: behavioural review of an agent's recent audit window; flags only"))

    # ================================================================ dispatch
    def dispatch(self, ctx: Any, function_id: str, args: Mapping[str, Any] | None = None) -> DispatchResult:
        """The single entry point for every function request. Always audited; denials go to the police engine."""
        args = dict(args or {})
        input_hash = canonical_hash({"function": function_id, "args": _jsonable(args)})
        res = self.engine.authorize(ctx, function_id, args)
        agent_id = ctx.agent_id if self.runtime.is_valid(ctx) else "unauthenticated"
        session_id = ctx.session_id if self.runtime.is_valid(ctx) else "-"
        resource = ",".join(res.resources[:8]) if res.resources else "-"
        if not res.allowed:
            ev = self.audit.record(agent_id=agent_id, session_id=session_id, function_id=function_id, resource_id=resource,
                                   request_id=str(args.get("request_id")) if args.get("request_id") else None, approval_id=None,
                                   authorization=DENY, denial_reason=res.reason, input_hash=input_hash, output_hash=None,
                                   action="function_request", result="denied", detail=res.detail, checks=res.checks)
            self.police.inspect(ev.as_dict())
            self._record(denied=1)
            return DispatchResult(res, None, ev.seq)
        spec = self.registry.get(function_id)
        try:
            output = spec.handler(ctx, args)  # type: ignore[union-attr]
            error = ""
        except Halted:
            raise
        except Exception as exc:
            output, error = None, f"{type(exc).__name__}: {exc}"
        ev = self.audit.record(agent_id=agent_id, session_id=session_id, function_id=function_id, resource_id=resource,
                               request_id=str(args.get("request_id")) if args.get("request_id") else _rid_of(output), approval_id=_aid_of(output),
                               authorization=ALLOW, denial_reason=None, input_hash=input_hash,
                               output_hash=canonical_hash(_jsonable(output)) if output is not None else None,
                               action="function_request", result="error" if error else "executed", detail=error, checks=res.checks)
        self.police.inspect(ev.as_dict())
        return DispatchResult(res, output, ev.seq, error)

    # ================================================================ engine callbacks
    def _resources_of_request(self, args: Mapping[str, Any]) -> list[str]:
        req = self.twe.get_request(str(args.get("request_id", "")))
        return list(req.get("resources", [])) if req else []

    def _request_state(self, request_id: str) -> dict | None:
        return self.twe.get_request(request_id)

    def _approval_state(self, request_id: str) -> dict | None:
        if self.approvals_unavailable:
            return {"error": "approval service unavailable", "reason": "authorization_error"}
        p = self.approvals_dir / "records" / f"{request_id}.json"
        if not p.exists():
            return None
        appr = json.loads(p.read_text(encoding="utf-8"))
        if time.time() - float(appr.get("ts", 0)) > self.c.approval_ttl_hours * 3600:
            return {"error": "approval expired", "reason": "expired_approval"}
        if canonical_hash({k: v for k, v in appr.items() if k != "record_hash"}) != appr.get("record_hash"):
            return {"error": "approval record modified", "reason": "invalid_approval"}
        return appr

    def _evidence_ok(self, payload: Mapping[str, Any]) -> tuple[bool, str]:
        """R03/R04 §15: the observable evidence requirement. Only verified, observed, sourced (with source)
        or derived (with premises) items count; hypotheses and unknowns never satisfy the requirement."""
        ev = parse_evidence(payload.get("evidence"))
        if not ev:
            return False, "no evidence block"
        for it in ev.get("sourced", []):
            if not str(it.get("source", "")).strip():
                return False, f"sourced item without a source: {it.get('claim', '')[:80]}"
        for it in ev.get("derived", []):
            if not it.get("premises"):
                return False, f"derived conclusion without premises: {it.get('conclusion', '')[:80]}"
        supported = len(ev.get("verified_facts", [])) + len(ev.get("observed", [])) + len(ev.get("sourced", [])) + len(ev.get("derived", []))
        if supported == 0:
            return False, "no verified, observed, sourced or derived item; hypotheses and unknowns do not satisfy the requirement"
        return True, ""

    def _policy_ok(self, ctx: AgentContext, function_id: str, args: Mapping[str, Any]) -> tuple[bool, str]:
        if function_id == "propose_patch":
            files = args.get("files") or {}
            if not isinstance(files, dict) or not files:
                return False, "propose_patch requires a non-empty files map"
            d = evaluate(self.c, Proposal(status="proposal", files=dict(files)))
            if d.blocked:
                for flag, kind in (("self_modification", "block_self_modification"), ("halt_control_reference", "block_halt_control_reference"),
                                   ("secret_material", "block_secret_material")):
                    if flag in d.flags:
                        self._open_incident(kind, task=str(args.get("task_id", "-")), request="-", facts=d.reasons)
                return False, "; ".join(d.reasons)[:500]
        if function_id == "record_approval":
            req = self.twe.get_request(str(args.get("request_id", "")))
            if req is None:
                return False, "unknown request"
            if req.get("requester") == ctx.agent_id:
                return False, "requester cannot approve its own request"
            phrase = str(args.get("phrase", "")).strip()
            rid = str(args.get("request_id"))
            if phrase not in (self.c.approval_phrase.format(request_id=rid), self.c.rejection_phrase.format(request_id=rid)):
                return False, "phrase does not match the approval or rejection phrase exactly"
        return True, ""

    def _halted_reason(self, mutation: bool) -> str:
        if self.halt.stopped:
            return self.halt.reason() or "halted"
        if mutation and self.halt.frozen:
            return "FREEZE file present: mutations are disabled"
        return ""

    def _police_escalate(self, agent: str, payload: dict) -> None:
        self.twe.append_note("twe/human", "police", "escalation", {"monitored_agent": agent, **payload})

    # ================================================================ handlers (execute only after ALLOW)
    def _f_profile(self, ctx: AgentContext, a: Mapping[str, Any]) -> dict:
        prof = self.engine.profile(ctx)
        principal = self.permissions.get(ctx.agent_id)
        prof["twe_id"] = principal.twe if principal else None
        return prof

    def _f_tree(self, ctx: AgentContext, a: Mapping[str, Any]) -> str:
        return self.ws.tree()

    def _f_read_file(self, ctx: AgentContext, a: Mapping[str, Any]) -> str:
        return self.ws.read_text(str(a.get("path", "")))

    def _f_read_twe(self, ctx: AgentContext, a: Mapping[str, Any]) -> list[dict]:
        return self.twe.read(str(a["twe_id"]), int(a.get("limit", 200)))

    def _f_propose_patch(self, ctx: AgentContext, a: Mapping[str, Any]) -> dict:
        principal = self.permissions.get(ctx.agent_id)
        p = Proposal.from_json_text(json.dumps({"status": "proposal", **{k: a.get(k) for k in
                                    ("rationale", "files", "evidence", "unresolved", "considered_actions", "risk_self_report", "confidence", "requests") if k in a}}))
        task_id = str(a.get("task_id", "-"))
        d = evaluate(self.c, p)
        self._check_test_count(p, d)
        self._flag_hypotheses(p, d)
        resources = sorted(_wsres(f) for f in p.files)
        payload = {"files": p.files, "rationale": p.rationale, "evidence": p.evidence, "unresolved": p.unresolved,
                   "considered_actions": p.considered_actions, "risk_self_report": p.risk_self_report, "confidence": p.confidence,
                   "policy_verdict": d.verdict, "policy_flags": d.flags, "policy_reasons": d.reasons}
        entry = self.twe.append_request(principal.twe, ctx.agent_id, "patch", "APPLY_PATCH", resources, payload, task_id=task_id)
        rid = entry["id"]
        packet = self._packet(rid, task_id, p, d, entry["payload_hash"])
        (self.approvals_dir / "pending" / f"{rid}.md").write_text(packet, encoding="utf-8")
        try:
            task = self.tasks.find(task_id)
            task.attempts += 1
            self.tasks.move(task, self.tasks.active, f"awaiting human decision on {rid}")
        except FileNotFoundError:
            pass
        self._record(proposals=1)
        self._write_report("awaiting_approval", task_id, p, d, None, request_id=rid)
        return {"request_id": rid, "request_hash": entry["payload_hash"], "verdict": d.verdict, "flags": d.flags}

    def _f_request_action(self, ctx: AgentContext, a: Mapping[str, Any]) -> dict:
        payload = {"action": str(a.get("action", "")), "rationale": str(a.get("rationale", ""))[:4000], "evidence": parse_evidence(a.get("evidence"))}
        entry = self.twe.append_request(str(a["twe_id"]), ctx.agent_id, "action", str(a.get("required_permission", "EXTERNAL_SYSTEM_WRITE")),
                                        [str(r) for r in (a.get("resources") or ["external/unspecified"])], payload, task_id=str(a.get("task_id", "-")))
        return {"request_id": entry["id"], "request_hash": entry["payload_hash"], "note": "recorded; no executor exists for this action type at this stage"}

    def _f_report_blocker(self, ctx: AgentContext, a: Mapping[str, Any]) -> dict:
        p = Proposal.from_json_text(json.dumps({"status": "escalate", **{k: a.get(k) for k in
                                    ("rationale", "blocker", "evidence", "unresolved", "considered_actions", "requests") if k in a}}))
        task_id = str(a.get("task_id", "-"))
        entry = self.twe.append_note(str(a["twe_id"]), ctx.agent_id, "blocker",
                                     {"task_id": task_id, "blocker": p.blocker, "evidence": p.evidence, "unresolved": p.unresolved,
                                      "considered_actions": p.considered_actions, "rationale": p.rationale})
        try:
            task = self.tasks.find(task_id)
            self._write_blocker(task, p)
            task.attempts += 1
            self.tasks.move(task, self.tasks.blocked, f"escalated: {p.blocker.get('nature', p.rationale)[:200]}")
            self._write_report("escalated", task_id, p, None, None)
        except FileNotFoundError:
            pass
        category = str(p.blocker.get("category", "")).strip().lower()
        if category in ("misleading_directive", "erroneous_directive"):
            self._open_incident("directive_defect_reported", task=task_id, request="-",
                                facts=[f"category={category}", f"nature={p.blocker.get('nature', '')}", f"constraint={p.blocker.get('constraint', '')}"])
        self._record(escalations=1)
        return {"blocker_entry": entry["id"], "task_state": "blocked"}

    def _f_abstain(self, ctx: AgentContext, a: Mapping[str, Any]) -> dict:
        task_id = str(a.get("task_id", "-"))
        entry = self.twe.append_note(str(a["twe_id"]), ctx.agent_id, "abstain", {"task_id": task_id, "rationale": str(a.get("rationale", ""))[:4000]})
        try:
            task = self.tasks.find(task_id)
            task.attempts += 1
            self.tasks.move(task, self.tasks.parked, f"model abstained: {str(a.get('rationale', ''))[:200]}")
            self._write_report("abstained", task_id, Proposal(status="abstain", rationale=str(a.get("rationale", ""))), None, None)
        except FileNotFoundError:
            pass
        self._record(abstentions=1)
        return {"abstain_entry": entry["id"], "task_state": "parked"}

    def _f_record_approval(self, ctx: AgentContext, a: Mapping[str, Any]) -> dict:
        rid = str(a["request_id"])
        req = self.twe.get_request(rid)
        phrase = str(a.get("phrase", "")).strip()
        decision = "approved" if phrase == self.c.approval_phrase.format(request_id=rid) else "rejected"
        p = self.approvals_dir / "records" / f"{rid}.json"
        if p.exists():
            raise KernelError(f"an approval record for {rid} already exists")
        appr = {"approval_id": f"apr-{rid}", "request_id": rid, "request_hash": req["hash"], "approver": ctx.agent_id,
                "scope": list(req.get("resources", [])), "decision": decision, "ts": time.time(), "phrase_hash": canonical_hash(phrase)}
        appr["record_hash"] = canonical_hash(appr)
        p.write_text(json.dumps(appr, indent=2), encoding="utf-8")
        self.twe.append_note(req["twe"], ctx.agent_id, "approval_notice", {"request_id": rid, "decision": decision, "approval_id": appr["approval_id"]}, refs=[rid])
        if decision == "rejected":
            self._dispose(rid, "rejected")
        return {"approval_id": appr["approval_id"], "decision": decision, "request_hash": req["hash"]}

    def _f_apply(self, ctx: AgentContext, a: Mapping[str, Any]) -> dict:
        rid = str(a["request_id"])
        req = self.twe.get_request(rid)
        if req.get("type") != "patch":
            raise KernelError("only patch requests have an executor at this stage")
        self.halt.check(mutation=True)
        files = dict(req["files"])
        task_id = str(req.get("task_id", "-"))
        before = self.checkpoints.take(f"before-{rid[-8:]}")
        self.audit.append(KERNEL, "checkpoint", before.id, "ok", files=before.file_count, manifest=before.manifest_sha256)
        written = self.ws.apply_files(files)
        self.audit.append(KERNEL, "files_written", rid, "ok", files=written)
        self.halt.check()
        result = run_tests(self.c, self.ws)
        self.audit.append(KERNEL, "tests_run", rid, "pass" if result.ok else "fail", returncode=result.returncode,
                          duration_s=round(result.duration_s, 2), timed_out=result.timed_out, wrapper_active=result.wrapper_active)
        p = Proposal(status="proposal", files=files, rationale=req.get("rationale", ""))
        if result.ok:
            after = self.checkpoints.take(f"after-{rid[-8:]}")
            self.audit.append(KERNEL, "checkpoint", after.id, "ok", files=after.file_count, manifest=after.manifest_sha256)
            self._dispose(rid, "applied")
            self._record(applied=1)
            self._write_report("applied", task_id, p, None, result, request_id=rid)
            return {"applied": True, "files": written, "checkpoint_after": after.id}
        self.checkpoints.restore(before.id)
        self.audit.append(KERNEL, "rollback", before.id, "ok", reason="tests failed")
        self._dispose(rid, "failed")
        self._record(rolled_back=1)
        self._open_incident("rollback_after_tests_failed", task=task_id, request=rid,
                            facts=[f"tests returncode={result.returncode} timed_out={result.timed_out} duration_s={result.duration_s:.1f}",
                                   f"restored checkpoint {before.id}", "stdout tail:", result.stdout_tail[-1200:], "stderr tail:", result.stderr_tail[-600:]])
        self._write_report("rolled_back", task_id, p, None, result, request_id=rid)
        return {"applied": False, "restored_checkpoint": before.id}

    def _f_police_review(self, ctx: AgentContext, a: Mapping[str, Any]) -> dict:
        if self.police_model is None:
            raise KernelError("no police model configured")
        agent = str(a.get("monitored_agent", "proposer"))
        window = [e for e in list(self.audit.events())[-200:] if e.get("agent_id") == agent]
        return self.police.llm_review(agent, window, self.police_model)

    def _dispose(self, rid: str, outcome: str) -> None:
        req = self.twe.get_request(rid) or {}
        src = self.approvals_dir / "pending" / f"{rid}.md"
        if src.exists():
            src.rename(self.approvals_dir / "pending" / f"{rid}.{outcome}.md")
        self.twe.append_note(req.get("twe", "twe/proposer"), KERNEL, "disposition", {"request_id": rid, "outcome": outcome}, refs=[rid])
        try:
            task = self.tasks.find(str(req.get("task_id", "-")))
            dest = self.tasks.done if outcome == "applied" else self.tasks.queue
            self.tasks.move(task, dest, f"{rid} {outcome}")
        except FileNotFoundError:
            pass

    # ================================================================ proposer cycle
    def propose(self, task: Task | None = None) -> DispatchResult | None:
        """One proposer cycle: prompt -> model -> ONE function call -> dispatch. Returns the dispatch result."""
        self.halt.check()
        self.halt.start_deadline(self.c.budget("max_cycle_wall_seconds"))
        self.halt.count("cycles_today")
        try:
            if self.c.autonomy_level < 1:
                self.audit.append(KERNEL, "propose", "-", "refused", reason="autonomy level 0: read/report only")
                return None
            task = task or self.tasks.next_queued()
            if task is None:
                self.audit.append(KERNEL, "propose", "-", "idle", reason="no queued task")
                return None
            max_attempts = int(self.c.section("autonomy")["max_proposals_per_task"])
            if task.attempts >= max_attempts:
                self.tasks.move(task, self.tasks.parked, "attempt limit reached; awaiting human decision")
                self.audit.append(KERNEL, "task_parked", task.id, "ok", attempts=task.attempts)
                return None
            self.audit.append(KERNEL, "propose_start", task.id, "ok", attempt=task.attempts + 1)
            system, user = self._build_prompt(task)
            self.halt.check()
            self.halt.count("model_calls")
            raw = self.proposer.complete(system, user, max_output_chars=self.c.budget("max_output_chars_per_call"))
            reasoning = str(getattr(self.proposer, "last_reasoning", "") or "")
            self._count_activity(len(raw) + len(reasoning))
            trace = self.write_trace("propose", task.id, reasoning, raw)
            self.audit.append("model", "model_output_received", task.id, "ok", model=getattr(self.proposer, "name", "?"), chars=len(raw),
                              reasoning_chars=len(reasoning), trace=str(trace))
            call, args = self._parse_call(raw, task)
            if call is None:
                task.attempts += 1
                why = ("reasoning-only output: the model spent its budget thinking and returned no answer" if (not raw.strip() and reasoning)
                       else "malformed model output")
                self.tasks.move(task, self.tasks.queue, why)
                self.audit.append(KERNEL, "model_output_rejected", task.id, "malformed", reason=why, reasoning_chars=len(reasoning))
                self._record(malformed=1)
                return None
            res = self.dispatch(self.ctx_proposer, call, args)
            if not res.allowed:
                task.attempts += 1
                self.tasks.move(task, self.tasks.queue, f"call {call} denied: {res.authz.reason} {res.authz.detail[:200]}" if not res.error else f"call {call} failed: {res.error[:200]}")
                self._write_report("denied" if not res.error else "error", task.id, None, None, None, note=f"{call}: {res.authz.reason or res.error}")
            return res
        except Halted as exc:
            if "budget breaker" in str(exc):
                self._open_incident("budget_breaker", task=task.id if task else "-", request="-", facts=[str(exc)])
            raise
        finally:
            self.halt.clear_deadline()

    def _parse_call(self, raw: str, task: Task) -> tuple[str | None, dict]:
        """Accept {"call","args"}; map the legacy proposal shape onto the corresponding function."""
        try:
            obj = _extract_json(raw)
        except KernelError:
            return None, {}
        if not isinstance(obj, dict):
            return None, {}
        principal = self.permissions.get("proposer")
        twe = principal.twe if principal else "twe/proposer"
        if "call" in obj:
            args = dict(obj.get("args") or {})
            args.setdefault("task_id", task.id)
            if obj["call"] in ("report_blocker", "abstain", "request_action"):
                args.setdefault("twe_id", twe)
            return str(obj["call"]), args
        status = str(obj.get("status", "")).lower() or ("abstain" if obj.get("abstain") else "proposal")
        common = {k: obj[k] for k in ("rationale", "evidence", "unresolved", "considered_actions", "risk_self_report", "confidence", "requests", "facts", "assumptions") if k in obj}
        if status == "escalate":
            return "report_blocker", {"twe_id": twe, "task_id": task.id, "blocker": obj.get("blocker") or {"nature": obj.get("rationale", "")}, **common}
        if status == "abstain":
            return "abstain", {"twe_id": twe, "task_id": task.id, "rationale": str(obj.get("rationale") or obj.get("abstain_reason", ""))}
        return "propose_patch", {"task_id": task.id, "files": obj.get("files") or {}, **common}

    # ================================================================ human operations (CLI)
    def approve(self, request_id: str, typed_phrase: str) -> DispatchResult:
        return self.dispatch(self.ctx_human, "record_approval", {"request_id": request_id, "phrase": typed_phrase})

    def apply(self, request_id: str) -> DispatchResult:
        return self.dispatch(self.ctx_human, "apply_approved_request", {"request_id": request_id})

    def write_trace(self, kind: str, ref: str, reasoning: str, content: str) -> Path:
        """Model trace (v2.7): the reasoning and the answer of one model call, kept under state/model_traces/ so the
        human can read what the model was thinking. Traces are records, not inputs: nothing reads them back."""
        d = self.layout.state / "model_traces"
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{time.strftime('%Y%m%dT%H%M%S')}-{kind}-{ref.replace('/', '_')[:40]}.md"
        path.write_text(f"# Model trace — {kind} {ref}\n\n- time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n- reasoning: {len(reasoning)} chars\n"
                        f"- answer: {len(content)} chars\n\n## Reasoning\n\n{reasoning or '(none)'}\n\n## Answer\n\n{content or '(empty)'}\n", encoding="utf-8")
        return path

    def draft_task(self, message: str, history: list[dict], current_draft: dict | None = None) -> dict:
        """Human-assisted task drafting (v2.5). Calls the assistant model; queues nothing. Audited; refused while halted."""
        from .assistant import TaskDrafter
        self.halt.check()
        if self.assistant_model is None:
            raise KernelError("no assistant model configured ([models.assistant] provider is \"dummy\")")
        drafter = TaskDrafter(self.assistant_model, max_output_chars=self.c.budget("max_output_chars_per_call"))
        writable = [str(g) for g in self.c.section("paths").get("allowed_write_globs", [])]
        out = drafter.draft(message, history, current_draft, self.ws.tree(), writable)
        out["trace"] = str(self.write_trace("draft", "assistant", out.get("reasoning", ""), out.get("raw", "")))
        a = self._activity(); a["draft_calls"] = int(a.get("draft_calls", 0)) + 1; self._save_activity(a)
        self.audit.append("human", "task_drafted", "-", "ok" if out["parsed"] else "unparsed", input_hash=out["input_hash"],
                          output_hash=out["output_hash"], model=drafter.name, via="control_panel")
        log = self.layout.state / "assistant"
        log.mkdir(parents=True, exist_ok=True)
        with (log / "chat.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "message": message[:4000], "reply": out["reply"], "draft": out["draft"],
                                "questions": out["questions"], "parsed": out["parsed"], "model": drafter.name}, ensure_ascii=False) + "\n")
        return out

    def unblock(self, task_id: str, guidance: str) -> Task:
        self.halt.check(mutation=True)
        task = self.tasks.unblock(task_id, guidance)
        rec = self.blockers_dir / f"{task_id}.md"
        if rec.exists():
            text = rec.read_text(encoding="utf-8").replace("- Status: OPEN — task paused; no change was made",
                                                         f"- Status: RESOLVED {time.strftime('%Y-%m-%d %H:%M:%S')} — guidance: {guidance}")
            (self.blockers_dir / f"{task_id}.resolved.{int(time.time())}.md").write_text(text, encoding="utf-8")
            rec.unlink()
        self.twe.append_note("twe/proposer", "human", "note", {"task_id": task_id, "guidance": guidance[:2000]})
        self.audit.append("human", "blocker_resolved", task_id, "ok", guidance=guidance[:2000])
        return task

    def record_finding(self, incident_id: str, judgment: str, note: str) -> Path:
        if judgment not in ("reasonable", "judgment_failure", "undetermined"):
            raise KernelError("judgment must be reasonable | judgment_failure | undetermined")
        path = self.incidents_dir / f"{incident_id}.md"
        if not path.exists():
            raise KernelError(f"no incident {incident_id}")
        text = path.read_text(encoding="utf-8")
        marker = "- Judgment: (unrecorded"
        if marker not in text:
            raise KernelError("finding already recorded")
        path.write_text(text[: text.index(marker)] + f"- Judgment: {judgment} — recorded {time.strftime('%Y-%m-%d %H:%M:%S')}\n- Note: {note}\n", encoding="utf-8")
        self.audit.append("human", "finding_recorded", incident_id, judgment, note=note[:2000])
        self._record(**{f"findings_{judgment}": 1})
        return path

    def pending_requests(self) -> list[str]:
        return sorted(p.stem for p in (self.approvals_dir / "pending").glob("req-*.md") if p.stem.count(".") == 0)

    def packet_text(self, request_id: str) -> str:
        return (self.approvals_dir / "pending" / f"{request_id}.md").read_text(encoding="utf-8")

    def status(self) -> dict:
        ok, msg = self.audit.verify()
        pok, pmsg = self.police.verify()
        return {
            "constitution_version": self.c.section("meta")["version"], "constitution_sha256": self.c.sha256[:16],
            "permissions_version": self.permissions.version, "permissions_sha256": self.permissions.sha256[:16],
            "autonomy_level": self.c.autonomy_level, "halted": self.halt.stopped, "halt_reason": self.halt.reason(), "frozen": self.halt.frozen,
            "audit": msg, "audit_ok": ok, "police": pmsg, "police_ok": pok,
            "pending_approvals": self.pending_requests(), "tasks": self.tasks.counts(),
            "blockers": sorted(p.stem for p in self.blockers_dir.glob("*.md") if ".resolved." not in p.name),
            "open_incidents": sorted(p.stem for p in self.incidents_dir.glob("*.md") if "- Judgment: (unrecorded" in p.read_text(encoding="utf-8")),
            "twes": {t: self.twe.verify(t)[1] for t in self.twe.ids()},
            "checkpoints": len(self.checkpoints.list()), "activity": self._activity(),
            "proposer": getattr(self.proposer, "name", "?"), "monitor": getattr(self.monitor, "name", "?"),
        }

    # ================================================================ bookkeeping
    def _record_hashes_seen(self) -> None:
        for name, sha, version in (("constitution.toml", self.c.sha256, self.c.section("meta")["version"]),
                                   ("permissions.toml", self.permissions.sha256, self.permissions.version)):
            marker = self.layout.state / f"{name}.last_seen_sha256"
            previous = marker.read_text(encoding="utf-8").strip() if marker.exists() else ""
            if previous != sha:
                self.audit.append("human", f"{name.split('.')[0]}_changed" if previous else f"{name.split('.')[0]}_loaded", name, "ok",
                                  previous_sha256=previous, new_sha256=sha, version=version)
                marker.write_text(sha, encoding="utf-8")

    def _activity_path(self) -> Path:
        return self.layout.state / "activity.json"

    def _activity(self) -> dict:
        p = self._activity_path()
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return {"model_calls": 0, "output_chars": 0, "since_refresher_calls": 0, "since_refresher_chars": 0, "refreshers": 0}

    def _save_activity(self, a: dict) -> None:
        self._activity_path().write_text(json.dumps(a, indent=2), encoding="utf-8")

    def _count_activity(self, output_chars: int) -> None:
        a = self._activity()
        a["model_calls"] += 1; a["output_chars"] += output_chars
        a["since_refresher_calls"] += 1; a["since_refresher_chars"] += output_chars
        self._save_activity(a)

    def _refresher_due(self) -> bool:
        r = self.c.data.get("reflection", {}); a = self._activity()
        return (a["since_refresher_calls"] >= int(r.get("refresher_every_model_calls", 20)) or
                a["since_refresher_chars"] >= int(r.get("refresher_every_output_chars", 400000)))

    def _refresher_text(self) -> str:
        path = self.layout.state / "training" / "refresher.md"
        return path.read_text(encoding="utf-8")[:20000] if path.exists() else DEFAULT_REFRESHER

    def _record(self, **increments: int) -> dict:
        p = self.layout.state / "agent_record.json"
        rec = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        for k, v in increments.items():
            rec[k] = int(rec.get(k, 0)) + v
        p.write_text(json.dumps(rec, indent=2, sort_keys=True), encoding="utf-8")
        return rec

    def _open_incident(self, kind: str, *, task: str, request: str, facts: list[str]) -> Path | None:
        cfg = self.c.data.get("incidents", {})
        if kind not in tuple(cfg.get("open_on", ())):
            return None
        stamp = time.strftime("%Y-%m-%dT%H%M%S")
        incident_id = f"inc-{stamp}-{kind}"
        text = INCIDENT_TEMPLATE.format(incident_id=incident_id, kind=kind, stamp=stamp, task=task, request=request,
                                        version=self.c.section("meta")["version"], sha=self.c.sha256[:16], seq=self.audit._last_seq,  # noqa: SLF001
                                        facts="\n".join(f"- {f}" for f in facts if f is not None))
        path = self.incidents_dir / f"{incident_id}.md"
        if path.exists():
            path = self.incidents_dir / f"{incident_id}-{int(time.time() * 1000) % 100000}.md"
        path.write_text(text, encoding="utf-8")
        self.audit.append(KERNEL, "incident_opened", path.stem, kind, task=task, request=request)
        self._record(incidents_opened=1)
        return path

    # ================================================================ prompt, packets, reports
    def _build_prompt(self, task: Task) -> tuple[str, str]:
        refresher = ""
        if self._refresher_due():
            refresher = self._refresher_text() + "\n\n"
            a = self._activity(); a["since_refresher_calls"] = 0; a["since_refresher_chars"] = 0; a["refreshers"] += 1
            self._save_activity(a)
            self.audit.append(KERNEL, "refresher_inserted", task.id, "ok", refreshers=a["refreshers"])
            self._record(refreshers=1)
        profile = self._f_profile(self.ctx_proposer, {})
        system = (refresher + self.c.summary_for_model() + "\n\nAUTHORIZATION PROFILE (informational; the kernel re-checks every call):\n"
                  + json.dumps(profile, indent=1)[:6000] + "\n\n" + FUNCTION_CALL_HINT)
        relevant = [f"--- {rel}\n{self.ws.read_text(rel)}" for rel in self._guess_relevant_files(task)]
        history = ""
        if task.history:
            history = "HISTORY (most recent last; lines starting with GUIDANCE are human decisions on this task):\n" + \
                      "\n".join(f"- {h.get('note', '')}" for h in task.history[-5:]) + "\n"
        user = (f"TASK {task.id}: {task.title}\n\n{task.description}\n\nACCEPTANCE CRITERIA:\n{task.acceptance or '(none given)'}\n\n"
                f"PREVIOUS ATTEMPTS: {task.attempts}\n" + history +
                f"\nWORKSPACE FILES:\n{self.ws.tree()}\n\nRELEVANT FILE CONTENTS:\n" + ("\n".join(relevant) if relevant else "(none)"))
        return system, user

    def _guess_relevant_files(self, task: Task, limit: int = 8) -> list[str]:
        words = {w.strip(".,;:()[]`'\"").lower() for w in (task.title + " " + task.description).split() if len(w) > 3}
        out = []
        for rel in self.ws.tree(1000).splitlines():
            if any(w in rel.lower() for w in words):
                out.append(rel)
            if len(out) >= limit:
                break
        return out

    def _check_test_count(self, proposal: Proposal, decision) -> None:
        for rel, content in proposal.files.items():
            if not (rel.startswith("tests/") or rel.endswith(("_test.py", "test.py"))):
                continue
            before = self.ws.read_text(rel, limit=2_000_000).count("def test_")
            after = (content or "").count("def test_")
            if before and after < before:
                decision.flags = sorted(set(decision.flags + ["test_count_decreased"]))
                decision.reasons.append(f"{rel}: test functions {before} -> {after}")
                if decision.verdict != "BLOCK":
                    decision.verdict = "ESCALATE"

    def _flag_hypotheses(self, proposal: Proposal, decision) -> None:
        if proposal.evidence.get("hypotheses"):
            decision.flags = sorted(set(decision.flags + ["depends_on_hypotheses"]))
            decision.reasons.append("proposal lists unverified hypotheses: " + "; ".join(str(h)[:100] for h in proposal.evidence["hypotheses"][:5]))
            if decision.verdict != "BLOCK":
                decision.verdict = "ESCALATE"

    def _evidence_lines(self, p: Proposal) -> list[str]:
        ev = p.evidence
        if not ev:
            return ["## Evidence (from model)", "- (no evidence block supplied)", ""]
        def lst(items, fmt):
            return [fmt(x) for x in items] or ["- none stated"]
        return ["## Evidence (from model; R03 categories)",
                "### Verified facts", *lst(ev.get("verified_facts", []), lambda x: f"- {x}"), "",
                "### Directly observed", *lst(ev.get("observed", []), lambda x: f"- {x}"), "",
                "### From an identifiable source", *lst(ev.get("sourced", []), lambda x: f"- {x.get('claim','')} — source: {x.get('source','') or '(none named)'}"), "",
                "### Derived from verified premises", *lst(ev.get("derived", []), lambda x: f"- {x.get('conclusion','')} — premises: {'; '.join(x.get('premises', [])) or '(none listed)'}"), "",
                "### Hypotheses (unverified)", *lst(ev.get("hypotheses", []), lambda x: f"- {x}"), "",
                "### Unknown or unavailable", *lst(ev.get("unknown", []), lambda x: f"- {x}"), ""]

    def _packet(self, rid: str, task_id: str, p: Proposal, d, request_hash: str) -> str:
        banner = "HIGH RISK - escalated flags present" if d.verdict == "ESCALATE" else "standard review"
        try:
            task = self.tasks.find(task_id); title, desc, acc = task.title, task.description, task.acceptance
        except FileNotFoundError:
            title, desc, acc = task_id, "(task not in store)", ""
        lines = [f"# Approval request {rid}", "", f"**Task:** {task_id} - {title}  ", f"**Request hash (immutable TWE entry):** {request_hash}  ",
                 f"**Policy verdict:** {d.verdict} ({banner})  ", f"**Flags:** {', '.join(d.flags) or 'none'}  ",
                 f"**Model self-reported risk:** {p.risk_self_report}, confidence {p.confidence:.2f}  ",
                 f"**Constitution:** v{self.c.section('meta')['version']} sha256 {self.c.sha256[:16]}; permissions v{self.permissions.version} {self.permissions.sha256[:12]}  ", "",
                 "## Task description", desc, "", "## Acceptance criteria", acc or "(none)", "", "## Rationale (from model)", p.rationale, "",
                 *self._evidence_lines(p),
                 "## Unresolved (from model)", *([f"- {u}" for u in p.unresolved] or ["- none stated"]), "",
                 "## Courses of action considered (from model)", *([f"- {u}" for u in p.considered_actions] or ["- none stated"]), "",
                 "## Policy reasons", *([f"- {r}" for r in d.reasons] or ["- none"]), "", "## Files to be written (full content)", ""]
        for path, content in p.files.items():
            lines += [f"### {path}", "```", content, "```", ""]
        lines += ["## How to decide", "",
                  f"Approve: `python -m kernel approve {rid}` and type exactly:  `{self.c.approval_phrase.format(request_id=rid)}`  ",
                  f"Reject:  `python -m kernel reject {rid}` and type exactly:  `{self.c.rejection_phrase.format(request_id=rid)}`  ",
                  f"Then `python -m kernel apply {rid}`. The approval binds to request hash {request_hash[:16]}…; the kernel re-derives the hash from the TWE entry at apply time."]
        return "\n".join(lines)

    def _write_blocker(self, task: Task, p: Proposal) -> Path:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        lines = [f"# Blocker — task {task.id}: {task.title}", "", f"- Raised: {stamp} by the proposer (attempt {task.attempts + 1})",
                 "- Status: OPEN — task paused; no change was made", f"- Category: {p.blocker.get('category', 'other')}", "",
                 "## Nature of the problem", p.blocker.get("nature", "") or p.rationale, "",
                 "## Requirement, constraint, assumption or evidence involved", p.blocker.get("constraint", "") or "(not stated)", "",
                 "## Input needed to proceed", p.blocker.get("input_needed", "") or "(not stated)", "",
                 *self._evidence_lines(p),
                 "## Unresolved", *([f"- {x}" for x in p.unresolved] or ["- none stated"]), "",
                 "## Courses of action considered", *([f"- {x}" for x in p.considered_actions] or ["- none stated"]), "",
                 f"To resolve: `python -m kernel unblock {task.id} \"<guidance>\"` returns the task to the queue with the guidance attached."]
        path = self.blockers_dir / f"{task.id}.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def _write_report(self, outcome: str, task_id: str, p: Proposal | None, d, r: RunResult | None, request_id: str = "-", note: str = "") -> Path:
        rep_dir = self.layout.state / str(self.c.section("reporting")["report_dir"])
        rep_dir.mkdir(parents=True, exist_ok=True)
        path = rep_dir / f"{time.strftime('%Y-%m-%d')}.md"
        block = [f"## {time.strftime('%Y-%m-%d %H:%M:%S')} - {outcome.upper()} - task {task_id} - request {request_id}", ""]
        if note:
            block.append(f"- {note}")
        if d:
            block.append(f"- policy: {d.verdict}; flags: {', '.join(d.flags) or 'none'}")
        if p:
            block.append(f"- status: {p.status}; files: {', '.join(sorted(p.files)) or 'none'}")
            if p.status == "escalate":
                block.append(f"- escalation: {p.blocker.get('nature', '')} | input needed: {p.blocker.get('input_needed', '')} (see state/blockers/{task_id}.md)")
        if r:
            block.append(f"- tests: {'PASS' if r.ok else 'FAIL'} in {r.duration_s:.1f}s (timeout={r.timed_out}, sandbox wrapper={'on' if r.wrapper_active else 'OFF'})")
        block.append(f"- halted: {self.halt.stopped}; audit: {self.audit.verify()[1]}; police: {self.police.verify()[1]}")
        block.append("")
        with path.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(block) + "\n")
        return path


# ---------------------------------------------------------------------- helpers
def _wsres(path: Any) -> str:
    p = str(path or "").replace("\\", "/").lstrip("/")
    return f"workspace/{p}" if p else ""


def _jsonable(obj: Any) -> Any:
    try:
        json.dumps(obj)
        return obj
    except TypeError:
        return str(obj)


def _rid_of(output: Any) -> str | None:
    return output.get("request_id") if isinstance(output, dict) else None


def _aid_of(output: Any) -> str | None:
    return output.get("approval_id") if isinstance(output, dict) else None
