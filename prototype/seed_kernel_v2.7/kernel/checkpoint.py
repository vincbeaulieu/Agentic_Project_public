"""Checkpoints: full, content-addressed snapshots of the workspace.

A checkpoint is a plain directory copy plus a manifest of SHA-256 hashes. It is
taken automatically BEFORE and AFTER every applied change, and can be restored
by a human with one command. Directory copies were selected over git for the seed kernel on three criteria:
inspectable without tooling; unaffected by the state of any git repository in the
workspace; not modifiable by a git command executed inside the workspace.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

IGNORE = shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".pytest_cache", "node_modules", ".venv", "venv")


@dataclass(frozen=True)
class Checkpoint:
    id: str
    path: Path
    label: str
    ts: float
    file_count: int
    manifest_sha256: str


def _manifest(root: Path) -> dict[str, str]:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and not any(part in ("__pycache__", ".git", ".pytest_cache") for part in p.parts):
            out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


class CheckpointStore:
    def __init__(self, state_dir: Path, workspace: Path) -> None:
        self.root = state_dir / "checkpoints"
        self.workspace = workspace
        self.root.mkdir(parents=True, exist_ok=True)

    def take(self, label: str) -> Checkpoint:
        ts = time.time()
        cid = time.strftime("%Y%m%dT%H%M%S", time.gmtime(ts)) + f"-{int((ts % 1) * 1000):03d}-{label}"
        dest = self.root / cid
        shutil.copytree(self.workspace, dest / "workspace", ignore=IGNORE, dirs_exist_ok=False)
        manifest = _manifest(dest / "workspace")
        mtext = json.dumps(manifest, sort_keys=True, indent=0)
        msha = hashlib.sha256(mtext.encode("utf-8")).hexdigest()
        meta = {"id": cid, "label": label, "ts": ts, "file_count": len(manifest), "manifest_sha256": msha}
        (dest / "manifest.json").write_text(mtext, encoding="utf-8")
        (dest / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return Checkpoint(cid, dest, label, ts, len(manifest), msha)

    def list(self) -> list[Checkpoint]:
        out = []
        for d in sorted(self.root.iterdir()):
            m = d / "meta.json"
            if m.exists():
                obj = json.loads(m.read_text(encoding="utf-8"))
                out.append(Checkpoint(obj["id"], d, obj["label"], obj["ts"], obj["file_count"], obj["manifest_sha256"]))
        return out

    def verify(self, cid: str) -> bool:
        d = self.root / cid
        stored = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        return stored == _manifest(d / "workspace")

    def restore(self, cid: str) -> None:
        """Replace the workspace with the checkpoint (a pre-restore checkpoint is taken first)."""
        src = self.root / cid / "workspace"
        if not src.exists():
            raise FileNotFoundError(cid)
        if not self.verify(cid):
            raise RuntimeError(f"checkpoint {cid} failed integrity verification; refusing to restore")
        self.take(f"pre-restore-of-{cid[:15]}")
        for child in self.workspace.iterdir():
            if child.name == ".git":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        shutil.copytree(src, self.workspace, ignore=IGNORE, dirs_exist_ok=True)

    def workspace_manifest_sha256(self) -> str:
        return hashlib.sha256(json.dumps(_manifest(self.workspace), sort_keys=True, indent=0).encode("utf-8")).hexdigest()
