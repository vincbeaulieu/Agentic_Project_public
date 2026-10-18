"""Task queue on the filesystem: one TOML file per task, moved between folders.

state/tasks/queue/    - waiting to be worked on (human writes these)
state/tasks/active/   - currently has a pending approval request
state/tasks/done/     - applied and tests passed
state/tasks/blocked/  - paused by an escalation; a blocker record exists in state/blockers/; awaits guidance
state/tasks/parked/   - attempt limit reached or model abstained; awaits a human decision
"""
from __future__ import annotations

import json
import time
try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore  (pip install tomli on Python 3.10)
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Task:
    id: str
    title: str
    description: str
    acceptance: str = ""
    priority: int = 5
    attempts: int = 0
    history: list[dict] = field(default_factory=list)
    path: Path | None = None

    def to_toml(self) -> str:
        def q(s: str) -> str:
            return json.dumps(s, ensure_ascii=False)
        hist = json.dumps(self.history, ensure_ascii=False)
        return (
            f"id = {q(self.id)}\ntitle = {q(self.title)}\npriority = {self.priority}\nattempts = {self.attempts}\n"
            f"description = {q(self.description)}\nacceptance = {q(self.acceptance)}\nhistory_json = {q(hist)}\n"
        )


class TaskStore:
    def __init__(self, state_dir: Path) -> None:
        self.root = state_dir / "tasks"
        self.queue, self.active, self.done, self.parked, self.blocked = (
            self.root / n for n in ("queue", "active", "done", "parked", "blocked"))
        for d in (self.queue, self.active, self.done, self.parked, self.blocked):
            d.mkdir(parents=True, exist_ok=True)

    def _load(self, p: Path) -> Task:
        obj = tomllib.loads(p.read_text(encoding="utf-8"))
        hist = json.loads(obj.get("history_json", "[]")) if obj.get("history_json") else obj.get("history", [])
        return Task(
            id=str(obj.get("id", p.stem)), title=str(obj.get("title", p.stem)), description=str(obj.get("description", "")),
            acceptance=str(obj.get("acceptance", "")), priority=int(obj.get("priority", 5)), attempts=int(obj.get("attempts", 0)),
            history=list(hist), path=p,
        )

    def add(self, task_id: str, title: str, description: str, acceptance: str = "", priority: int = 5) -> Task:
        t = Task(task_id, title, description, acceptance, priority)
        p = self.queue / f"{task_id}.toml"
        if p.exists():
            raise FileExistsError(task_id)
        p.write_text(t.to_toml(), encoding="utf-8")
        t.path = p
        return t

    def next_queued(self) -> Task | None:
        tasks = [self._load(p) for p in self.queue.glob("*.toml")]
        if not tasks:
            return None
        tasks.sort(key=lambda t: (t.priority, t.id))
        return tasks[0]

    def find(self, task_id: str) -> Task:
        for d in (self.queue, self.active, self.done, self.parked, self.blocked):
            p = d / f"{task_id}.toml"
            if p.exists():
                return self._load(p)
        raise FileNotFoundError(task_id)

    def move(self, task: Task, dest: Path, note: str) -> Task:
        task.history.append({"ts": time.time(), "to": dest.name, "note": note})
        new_path = dest / f"{task.id}.toml"
        new_path.write_text(task.to_toml(), encoding="utf-8")
        if task.path and task.path.exists() and task.path != new_path:
            task.path.unlink()
        task.path = new_path
        return task

    def unblock(self, task_id: str, guidance: str) -> Task:
        """Human guidance returns a blocked (or parked) task to the queue; the guidance is kept in history
        and shown to the proposer in the next prompt."""
        task = self.find(task_id)
        if task.path is None or task.path.parent not in (self.blocked, self.parked):
            raise ValueError(f"task {task_id} is not blocked or parked")
        return self.move(task, self.queue, f"GUIDANCE: {guidance}")

    def counts(self) -> dict[str, int]:
        return {d.name: len(list(d.glob("*.toml"))) for d in (self.queue, self.active, self.done, self.parked, self.blocked)}

    def all(self) -> dict[str, list[Task]]:
        """Every task by state (queue, active, done, parked, blocked), each list sorted by (priority, id)."""
        out = {}
        for d in (self.queue, self.active, self.done, self.parked, self.blocked):
            out[d.name] = sorted((self._load(p) for p in d.glob("*.toml")), key=lambda t: (t.priority, t.id))
        return out

    def next_id(self, prefix: str = "T-") -> str:
        """Next free id of the form T-NNN across all states (T-001 if none exists)."""
        n = 0
        for d in (self.queue, self.active, self.done, self.parked, self.blocked):
            for p in d.glob(f"{prefix}*.toml"):
                tail = p.stem[len(prefix):]
                if tail.isdigit():
                    n = max(n, int(tail))
        return f"{prefix}{n + 1:03d}"
