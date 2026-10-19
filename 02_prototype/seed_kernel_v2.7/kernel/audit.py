"""Append-only, hash-chained audit ledger (JSON Lines). Event schema per rule R04 §19.

Every event carries the SHA-256 of the previous event, so any edit, deletion or
reordering of past events breaks the chain and is detected by `verify()`.
The ledger lives in the kernel state directory, which the sandboxed workspace
cannot write to.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

GENESIS = "0" * 64


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _redact(obj: Any) -> Any:
    """Redact values whose keys match secret patterns before writing to the ledger."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if any(s in lk for s in ("api_key", "apikey", "secret", "password", "token_value", "authorization")):
                out[k] = "[REDACTED]"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [_redact(v) for v in obj]
    return obj


@dataclass(frozen=True)
class AuditEvent:
    seq: int
    ts: float
    actor: str
    agent_id: str
    session_id: str
    function_id: str
    resource_id: str
    request_id: str | None
    approval_id: str | None
    authorization: str | None
    denial_reason: str | None
    input_hash: str | None
    output_hash: str | None
    action: str
    target: str
    result: str
    details: dict
    constitution_sha256: str
    prev_hash: str
    hash: str

    def as_dict(self) -> dict:
        return dict(self.__dict__)


class AuditLedger:
    def __init__(self, path: Path, constitution_sha256: str) -> None:
        self.path = path
        self.constitution_sha256 = constitution_sha256
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._last_hash, self._last_seq = self._tail()

    # ------------------------------------------------------------------ write
    def append(self, actor: str, action: str, target: str, result: str, **details: Any) -> AuditEvent:
        """Legacy-style event (kernel-internal steps). Identity fields default to the actor."""
        return self.record(agent_id=actor, session_id=details.pop("session_id", "-"), function_id=details.pop("function_id", "-"),
                           resource_id=target, request_id=details.pop("request_id", None), approval_id=details.pop("approval_id", None),
                           authorization=details.pop("authorization", None), denial_reason=details.pop("denial_reason", None),
                           input_hash=details.pop("input_hash", None), output_hash=details.pop("output_hash", None),
                           action=action, result=result, **details)

    def record(self, *, agent_id: str, session_id: str, function_id: str, resource_id: str, request_id: str | None,
               approval_id: str | None, authorization: str | None, denial_reason: str | None, input_hash: str | None,
               output_hash: str | None, action: str, result: str, **details: Any) -> AuditEvent:
        """Full R04 §19 event. agent_id is always present; other fields may be None."""
        if not agent_id:
            raise ValueError("audit event requires agent_id")
        seq = self._last_seq + 1
        body = {
            "seq": seq,
            "ts": time.time(),
            "actor": agent_id,
            "agent_id": agent_id,
            "session_id": session_id or "-",
            "function_id": function_id or "-",
            "resource_id": resource_id or "-",
            "request_id": request_id,
            "approval_id": approval_id,
            "authorization": authorization,
            "denial_reason": denial_reason,
            "input_hash": input_hash,
            "output_hash": output_hash,
            "action": action,
            "target": resource_id or "-",
            "result": result,
            "details": _redact(details),
            "constitution_sha256": self.constitution_sha256,
            "prev_hash": self._last_hash,
        }
        h = hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()
        body["hash"] = h
        line = _canonical(body) + "\n"
        # O_APPEND so concurrent writers cannot interleave partial lines on POSIX.
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, line.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        self._last_hash, self._last_seq = h, seq
        return AuditEvent(**body)

    # ------------------------------------------------------------------- read
    def events(self) -> Iterator[dict]:
        if not self.path.exists():
            return iter(())
        with self.path.open("r", encoding="utf-8") as fh:
            return iter([json.loads(line) for line in fh if line.strip()])

    def _tail(self) -> tuple[str, int]:
        last_hash, last_seq = GENESIS, 0
        for ev in self.events():
            last_hash, last_seq = ev["hash"], ev["seq"]
        return last_hash, last_seq

    def verify(self) -> tuple[bool, str]:
        """Recompute the chain. Returns (ok, message)."""
        prev, expected_seq = GENESIS, 1
        for ev in self.events():
            if ev.get("seq") != expected_seq:
                return False, f"sequence gap at seq={ev.get('seq')} (expected {expected_seq})"
            if ev.get("prev_hash") != prev:
                return False, f"broken link at seq={ev['seq']}"
            body = {k: v for k, v in ev.items() if k != "hash"}
            h = hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()
            if h != ev.get("hash"):
                return False, f"modified event (hash mismatch) at seq={ev['seq']}"
            prev, expected_seq = h, expected_seq + 1
        return True, f"ok ({expected_seq - 1} events)"
