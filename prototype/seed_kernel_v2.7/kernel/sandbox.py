"""Workspace jail and constrained test execution.

The seed kernel does not implement an isolation technology; it uses what the
host provides and records in each report whether a wrapper was active:

* Path jail    - every write is resolved and must stay inside the workspace.
* Fixed command - only the constitution's test_command is ever executed; never
                  a string produced by a model.
* Stripped env - only allow-listed environment variables reach the test process
                 (so API keys in the kernel's environment are invisible to tests).
* Limits       - timeout always; RLIMIT_AS / RLIMIT_NPROC on POSIX when available.
* Optional wrapper - if the constitution's execution section provides a
                 `sandbox_wrapper` (e.g. ["docker","run",...], ["runsc",...],
                 ["bwrap",...], ["firejail",...]) the test command is prefixed
                 with it. This is how you plug in gVisor/Docker/microsandbox
                 instead of reinventing them.

Network isolation is not provided by the seed kernel on its own; it requires the
wrapper (e.g. `docker run --network none`). The report records whether a
wrapper was active.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from . import PolicyViolation
from .constitution import Constitution


@dataclass
class RunResult:
    ok: bool
    returncode: int
    duration_s: float
    stdout_tail: str
    stderr_tail: str
    timed_out: bool
    wrapper_active: bool


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve_inside(self, rel: str) -> Path:
        candidate = (self.root / rel).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise PolicyViolation(f"path escapes workspace: {rel}") from exc
        if candidate.is_symlink():
            raise PolicyViolation(f"refusing to write through symlink: {rel}")
        return candidate

    def apply_files(self, files: dict[str, str]) -> list[str]:
        """Write the proposal's files. Caller has already checked policy + approval."""
        written = []
        for rel, content in files.items():
            dest = self.resolve_inside(rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8", newline="\n")
            written.append(rel)
        return written

    def tree(self, max_entries: int = 400) -> str:
        lines = []
        for p in sorted(self.root.rglob("*")):
            if any(part in ("__pycache__", ".git", ".pytest_cache", ".venv") for part in p.parts):
                continue
            if p.is_file():
                lines.append(p.relative_to(self.root).as_posix())
            if len(lines) >= max_entries:
                lines.append("... (truncated)")
                break
        return "\n".join(lines)

    def read_text(self, rel: str, limit: int = 20000) -> str:
        p = self.resolve_inside(rel)
        if not p.exists():
            return ""
        return p.read_text(encoding="utf-8", errors="replace")[:limit]


def _preexec(mem_mb: int, nproc: int):
    def fn() -> None:
        try:
            import resource  # POSIX only
            resource.setrlimit(resource.RLIMIT_AS, (mem_mb * 1024 * 1024, mem_mb * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_NPROC, (nproc, nproc))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        except Exception:
            pass
    return fn


def run_tests(c: Constitution, ws: Workspace) -> RunResult:
    ex = c.section("execution")
    cmd = list(ex["test_command"])
    if cmd and cmd[0] == "python":
        cmd[0] = sys.executable
    wrapper = list(ex.get("sandbox_wrapper", ()) or ())
    full = wrapper + cmd
    env = {k: v for k, v in os.environ.items() if k in set(ex["env_allowlist"])}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    timeout = c.budget("max_test_wall_seconds")
    kwargs: dict = {}
    if os.name == "posix" and not wrapper:
        kwargs["preexec_fn"] = _preexec(int(ex.get("max_test_memory_mb", 1024)), int(ex.get("max_test_processes", 64)))
    t0 = time.monotonic()
    try:
        proc = subprocess.run(full, cwd=ws.root, env=env, capture_output=True, text=True, timeout=timeout, **kwargs)  # noqa: S603
        return RunResult(proc.returncode == 0, proc.returncode, time.monotonic() - t0, proc.stdout[-4000:], proc.stderr[-4000:], False, bool(wrapper))
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"")
        err = (exc.stderr or b"")
        out = out.decode("utf-8", "replace") if isinstance(out, bytes) else out
        err = err.decode("utf-8", "replace") if isinstance(err, bytes) else err
        return RunResult(False, -1, time.monotonic() - t0, out[-4000:], err[-4000:], True, bool(wrapper))
    except FileNotFoundError as exc:
        return RunResult(False, -2, time.monotonic() - t0, "", f"test command not found: {exc}", False, bool(wrapper))
