"""Halt controller: every way to stop the kernel, all of them outside the model loop.

Four independent mechanisms, any one of which is sufficient:

1. STOP file   - a human (or a monitor) creates <state>/STOP. Checked before every
                 step. Contains a reason. Removed only by the `resume` command,
                 which requires the resume phrase typed by a human.
2. OS signals  - SIGINT / SIGTERM set the flag immediately (Ctrl-C, kill, service stop).
3. Budgets     - circuit breakers on model calls, wall-clock, cycles/day.
                 Tripping one writes the STOP file itself (soft halt) so the kernel
                 stays stopped until a human looks.
4. FREEZE file - <state>/FREEZE allows reading/reporting but blocks every mutation
                 (apply, checkpoint restore, task state changes).

These files are not included in model input and are outside the model's write scope.
"""
from __future__ import annotations

import signal
import threading
import time
from pathlib import Path

from . import Halted


class HaltController:
    def __init__(self, state_dir: Path, *, install_signal_handlers: bool = True) -> None:
        self.state_dir = state_dir
        self.stop_file = state_dir / "STOP"
        self.freeze_file = state_dir / "FREEZE"
        self._flag = threading.Event()
        self._reason = ""
        self._deadline: float | None = None
        self._counters: dict[str, int] = {}
        self._limits: dict[str, int] = {}
        if install_signal_handlers:
            self._install()

    # ------------------------------------------------------------ mechanisms
    def _install(self) -> None:
        def handler(signum, frame):  # noqa: ANN001
            self.request_stop(f"signal {signum}")
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):
                # Not in main thread / unsupported platform: the STOP file still works.
                pass

    def request_stop(self, reason: str, *, persist: bool = True) -> None:
        self._reason = reason
        self._flag.set()
        if persist:
            self.write_stop_file(reason)

    def write_stop_file(self, reason: str) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with self.stop_file.open("a", encoding="utf-8") as fh:
            fh.write(f"{stamp}  {reason}\n")

    def set_limit(self, name: str, limit: int) -> None:
        self._limits[name] = limit
        self._counters.setdefault(name, 0)

    def count(self, name: str, n: int = 1) -> None:
        self._counters[name] = self._counters.get(name, 0) + n
        limit = self._limits.get(name)
        if limit is not None and self._counters[name] > limit:
            self.request_stop(f"budget breaker tripped: {name} > {limit}")
            self.check()

    def start_deadline(self, seconds: float) -> None:
        self._deadline = time.monotonic() + seconds

    def clear_deadline(self) -> None:
        self._deadline = None

    # ----------------------------------------------------------------- checks
    @property
    def stopped(self) -> bool:
        return self._flag.is_set() or self.stop_file.exists()

    @property
    def frozen(self) -> bool:
        return self.freeze_file.exists()

    def reason(self) -> str:
        if self._reason:
            return self._reason
        if self.stop_file.exists():
            try:
                return self.stop_file.read_text(encoding="utf-8").strip().splitlines()[-1]
            except (OSError, IndexError):
                return "STOP file present"
        return ""

    def check(self, *, mutation: bool = False) -> None:
        """Call before every step. Raises Halted if the kernel must not continue."""
        if self._deadline is not None and time.monotonic() > self._deadline:
            self.request_stop("budget breaker tripped: cycle wall-clock exceeded")
        if self.stopped:
            raise Halted(self.reason() or "halted")
        if mutation and self.frozen:
            raise Halted("FREEZE file present: mutations are disabled")

    # ---------------------------------------------------------------- resume
    def resume(self, typed_phrase: str, expected_phrase: str) -> bool:
        """Only a human typing the exact resume phrase clears the STOP file."""
        if typed_phrase.strip() != expected_phrase.strip():
            return False
        if self.stop_file.exists():
            archived = self.state_dir / f"STOP.cleared.{int(time.time())}"
            self.stop_file.rename(archived)
        self._flag.clear()
        self._reason = ""
        self._counters = {k: 0 for k in self._counters}
        return True
