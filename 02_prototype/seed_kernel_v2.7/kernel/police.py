"""Police subsystem (rule R04 §20–§28).

Two components, both without any authorization power:

PoliceEngine   deterministic, non-LLM. Every DENY audit event is passed to `inspect`, which
               classifies it by explicit rules, appends a hash-chained police event to
               state/police.jsonl, and, for classifications marked `escalate`, appends an
               escalation entry to the human's TWE. It also runs on ALLOW events to keep
               per-agent counters (repeated denials are counted over the recent window).

PoliceLLM      optional behavioural review of a window of audit events by a separate model.
               Its output is recorded as a police event with component "police_llm" and can
               only produce flags for investigation. There is no code path from its output to
               the authorization engine; `apply_verdict` is intentionally absent.

Nothing here can delete or modify audit or police history: the only write operation is append.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .authz import canonical_hash

GENESIS = "0" * 64

# classification rules: denial_reason -> (classification, severity, escalate)
RULES: dict[str, tuple[str, str, bool]] = {
    "unknown_function":        ("unauthorized_function", "medium", False),
    "missing_permission":      ("unauthorized_capability", "medium", False),
    "scope_violation":         ("unauthorized_resource_scope", "medium", False),
    "unknown_resource":        ("invalid_request", "low", False),
    "unknown_identity":        ("identity_failure", "high", True),
    "identity_mismatch":       ("identity_mismatch", "high", True),
    "unknown_request":         ("invalid_request", "low", False),
    "hash_mismatch":           ("request_approval_hash_mismatch", "high", True),
    "missing_approval":        ("missing_approval", "medium", False),
    "invalid_approval":        ("invalid_approval", "high", True),
    "expired_approval":        ("expired_approval", "medium", False),
    "rejected":                ("apply_of_rejected_request", "medium", False),
    "approval_scope_exceeded": ("approval_scope_exceeded", "high", True),
    "self_approval":           ("self_approval_attempt", "high", True),
    "missing_evidence":        ("evidence_requirement_unmet", "medium", False),
    "policy_block":            ("policy_block", "medium", False),
    "halted":                  ("call_while_halted", "low", False),
    "authorization_error":     ("authorization_service_failure", "high", True),
    "protected_resource":      ("protected_resource_access", "high", True),
    "security_state_access":   ("security_state_access", "high", True),
    "audit_modification":      ("audit_modification_attempt", "critical", True),
}
REPEAT_WINDOW = 20
REPEAT_THRESHOLD = 3


@dataclass
class PoliceEvent:
    seq: int
    ts: float
    monitored_agent: str
    triggering_event: int
    component: str
    classification: str
    severity: str
    action: str
    evidence: dict
    prev_hash: str
    hash: str


class PoliceEngine:
    def __init__(self, state_dir: Path, escalate: Callable[[str, dict], None] | None = None) -> None:
        self.path = state_dir / "police.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._escalate = escalate
        self._last_hash, self._last_seq = self._tail()

    def _events(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as fh:
            return [json.loads(l) for l in fh if l.strip()]

    def _tail(self) -> tuple[str, int]:
        h, s = GENESIS, 0
        for e in self._events():
            h, s = e["hash"], e["seq"]
        return h, s

    def _append(self, monitored_agent: str, triggering_event: int, component: str, classification: str, severity: str,
                action: str, evidence: dict) -> dict:
        body = {"seq": self._last_seq + 1, "ts": time.time(), "monitored_agent": monitored_agent, "triggering_event": triggering_event,
                "component": component, "classification": classification, "severity": severity, "action": action,
                "evidence": evidence, "prev_hash": self._last_hash}
        body["hash"] = canonical_hash(body)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o640)
        try:
            os.write(fd, (json.dumps(body, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")); os.fsync(fd)
        finally:
            os.close(fd)
        self._last_hash, self._last_seq = body["hash"], body["seq"]
        return body

    # ------------------------------------------------------------ deterministic
    def inspect(self, audit_event: dict) -> dict | None:
        """Called for every function-request audit event. Returns the police event for denials."""
        if audit_event.get("authorization") != "DENY":
            return None
        agent = str(audit_event.get("agent_id", "?"))
        reason = str(audit_event.get("denial_reason", "") or "unspecified")
        classification, severity, escalate = RULES.get(reason, ("unclassified_denial", "medium", True))
        recent = [e for e in self._events()[-REPEAT_WINDOW:] if e.get("monitored_agent") == agent and e.get("component") == "police_engine"]
        evidence = {"denial_reason": reason, "function_id": audit_event.get("function_id"), "resource_id": audit_event.get("resource_id"),
                    "detail": audit_event.get("details", {}).get("detail", ""), "recent_denials_by_agent": len(recent) + 1}
        action = "recorded"
        if len(recent) + 1 >= REPEAT_THRESHOLD:
            classification, severity, escalate = "repeated_denied_operations", "high", True
        ev = self._append(agent, int(audit_event.get("seq", 0)), "police_engine", classification, severity, action, evidence)
        if escalate and self._escalate is not None:
            self._escalate(agent, {"police_seq": ev["seq"], "classification": classification, "severity": severity, "evidence": evidence})
            ev["action"] = "escalated"
        return ev

    # ------------------------------------------------------------ police LLM
    def llm_review(self, monitored_agent: str, window: list[dict], model: Any, triggering_event: int = 0) -> dict:
        """Behavioural review by a separate model. Output is recorded as flags only.

        Whatever the model returns (including the strings ALLOW, SAFE or PERMIT), the result has
        no effect on any authorization decision: this method has no reference to the engine.
        """
        system = ("You are an independent monitoring function. Review a window of audit events for one agent and report "
                  "patterns for investigation: repeated attempts after denial, indirect access after denial, unreported "
                  "blockers, sequences inconsistent with the declared task. You cannot permit or deny anything. Respond with "
                  'ONE JSON object: {"flags": ["..."], "summary": "..."}')
        user = json.dumps(window[-50:], ensure_ascii=False)[:20000]
        raw = model.complete(system, user, max_output_chars=6000)
        try:
            obj = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
            flags = [str(f)[:200] for f in obj.get("flags", [])][:20]
            summary = str(obj.get("summary", ""))[:2000]
        except Exception:
            flags, summary = ["police_llm_unparsable"], raw[:500]
        return self._append(monitored_agent, triggering_event, "police_llm", "behavioural_review", "info",
                            "flagged" if flags else "no_flags", {"flags": flags, "summary": summary, "events_reviewed": len(window)})

    def verify(self) -> tuple[bool, str]:
        prev, expected = GENESIS, 1
        for e in self._events():
            if e.get("seq") != expected or e.get("prev_hash") != prev:
                return False, f"chain broken at seq={e.get('seq')}"
            body = {k: v for k, v in e.items() if k != "hash"}
            if canonical_hash(body) != e.get("hash"):
                return False, f"modified event at seq={e.get('seq')}"
            prev, expected = e["hash"], expected + 1
        return True, f"ok ({expected - 1} events)"

    def events(self) -> list[dict]:
        return self._events()
