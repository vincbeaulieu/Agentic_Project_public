"""TWE service: append-only, hash-chained team work environment logs (rule R04 §10–§13).

Storage: state/twe/<twe_id>.jsonl, one JSON object per line, each carrying the SHA-256 of the
previous entry. The service is the only component that touches these files. Agents reach
them exclusively through registered kernel functions (read_twe, request_action, propose_patch,
report_blocker, abstain), each authorized by the engine. There is no modify/delete/overwrite
operation in this module; a correction is a new entry referencing the previous one.

A request entry is immutable once appended: its `hash` is the canonical hash of its payload,
`get_request` returns both the stored hash and a recomputed hash, and the authorization engine
denies any operation on a request whose two hashes differ.
"""
from __future__ import annotations

import copy
import json
import os
import time
from pathlib import Path
from typing import Any, Iterator

from .authz import canonical_hash, new_request_id

GENESIS = "0" * 64
ENTRY_KINDS = ("request", "blocker", "abstain", "note", "escalation", "correction", "approval_notice", "disposition")


class TWEService:
    def __init__(self, state_dir: Path) -> None:
        self.root = state_dir / "twe"
        self.root.mkdir(parents=True, exist_ok=True)
        self._tails: dict[str, tuple[str, int]] = {}   # per-TWE (last hash, last seq), filled lazily

    # ------------------------------------------------------------- internals
    def _path(self, twe_id: str) -> Path:
        name = twe_id.split("/", 1)[1] if twe_id.startswith("twe/") else twe_id
        if not name or "/" in name or name.startswith("."):
            raise ValueError(f"invalid twe id {twe_id!r}")
        return self.root / f"{name}.jsonl"

    def _entries(self, twe_id: str) -> Iterator[dict]:
        p = self._path(twe_id)
        if not p.exists():
            return iter(())
        with p.open("r", encoding="utf-8") as fh:
            return iter([json.loads(line) for line in fh if line.strip()])

    def _tail(self, twe_id: str) -> tuple[str, int]:
        key = str(self._path(twe_id))
        if key not in self._tails:
            h, seq = GENESIS, 0
            for e in self._entries(twe_id):
                h, seq = e["hash"], e["seq"]
            self._tails[key] = (h, seq)
        return self._tails[key]

    def _append(self, twe_id: str, kind: str, author: str, payload: dict, entry_id: str | None = None, refs: list[str] | None = None) -> dict:
        if kind not in ENTRY_KINDS:
            raise ValueError(f"unknown entry kind {kind}")
        prev, seq = self._tail(twe_id)
        body = {
            "seq": seq + 1, "ts": time.time(), "twe": twe_id, "kind": kind, "id": entry_id or f"{kind}-{seq + 1}",
            "author": author, "payload": payload, "payload_hash": canonical_hash(payload), "refs": refs or [], "prev_hash": prev,
        }
        body["hash"] = canonical_hash(body)
        line = json.dumps(body, sort_keys=True, ensure_ascii=False) + "\n"
        fd = os.open(self._path(twe_id), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o640)
        try:
            os.write(fd, line.encode("utf-8")); os.fsync(fd)
        finally:
            os.close(fd)
        self._tails[str(self._path(twe_id))] = (body["hash"], body["seq"])
        return body

    # ----------------------------------------------------------- operations
    def read(self, twe_id: str, limit: int = 200) -> list[dict]:
        """Deep copies of the last `limit` entries; no handle or path is returned."""
        entries = list(self._entries(twe_id))[-limit:]
        return copy.deepcopy(entries)

    def append_request(self, twe_id: str, requester: str, request_type: str, required_permission: str,
                       resources: list[str], payload: dict, task_id: str = "-") -> dict:
        rid = new_request_id()
        body = {"request_id": rid, "type": request_type, "requester": requester, "required_permission": required_permission,
                "resources": sorted(resources), "task_id": task_id, **payload}
        return self._append(twe_id, "request", requester, body, entry_id=rid)

    def append_note(self, twe_id: str, author: str, kind: str, payload: dict, refs: list[str] | None = None) -> dict:
        return self._append(twe_id, kind, author, payload, refs=refs)

    def get_request(self, request_id: str) -> dict | None:
        """Locate a request in any TWE. Returns the payload plus stored and recomputed hashes."""
        for p in sorted(self.root.glob("*.jsonl")):
            for e in self._entries(f"twe/{p.stem}"):
                if e.get("kind") == "request" and e.get("id") == request_id:
                    body = {k: v for k, v in e.items() if k != "hash"}
                    out = copy.deepcopy(e["payload"])
                    out["hash"] = e["payload_hash"]
                    out["recomputed_hash"] = canonical_hash(e["payload"])
                    out["entry_hash"] = e["hash"]
                    out["entry_recomputed_hash"] = canonical_hash(body)
                    out["twe"] = e["twe"]
                    return out
        return None

    def verify(self, twe_id: str) -> tuple[bool, str]:
        prev, expected = GENESIS, 1
        for e in self._entries(twe_id):
            if e.get("seq") != expected or e.get("prev_hash") != prev:
                return False, f"chain broken at seq={e.get('seq')}"
            body = {k: v for k, v in e.items() if k != "hash"}
            if canonical_hash(body) != e.get("hash") or canonical_hash(e.get("payload", {})) != e.get("payload_hash"):
                return False, f"modified entry at seq={e.get('seq')}"
            prev, expected = e["hash"], expected + 1
        return True, f"ok ({expected - 1} entries)"

    def ids(self) -> list[str]:
        return sorted(f"twe/{p.stem}" for p in self.root.glob("*.jsonl"))
