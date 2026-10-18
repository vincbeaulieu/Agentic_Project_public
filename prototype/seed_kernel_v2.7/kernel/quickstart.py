"""Quickstart: seed a first workspace skeleton (empty workspace only) and the first self-build tasks (Stage 1, D3 §4.1).

With [paths] workspace_dir pointing at the platform (kernel v2.6), the tasks below are the first P1→P2 backlog items of
`platform/aop_platform_v0.1` (documentation first, then small queries with tests).

The workspace is the code the organization will build (the platform of D3 §4.5, `platform/` layer).
Tasks are ordered by risk class: documentation first (low), then small, testable code units.
Nothing here touches kernel/, constitution.toml, permissions.toml or state/ other than the task queue.
"""
from __future__ import annotations

from pathlib import Path

WORKSPACE_SKELETON = {
    "README.md": "# AOP platform workspace\n\nThis folder is built by the organization under the seed kernel's governance. "
                 "Every change arrives as a proposal, is reviewed and approved by the human, and is applied only if the tests pass.\n",
    "src/__init__.py": "",
    "src/aop/__init__.py": "\"\"\"AOP platform package (built under governance).\"\"\"\n__version__ = \"0.0.1\"\n",
    "tests/test_smoke.py": "import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))\n\n"
                           "from src.aop import __version__\n\n\ndef test_version_present():\n    assert __version__\n",
    "docs/README.md": "# Documentation\n\nArchitecture decision records live in docs/adr/. Each ADR has: context, options considered "
                      "(with the reuse search performed), decision, consequences, status, date.\n",
}

FIRST_TASKS = [
    ("T-001", "ADR-0007: single-writer lock for the organization store",
     "Create docs/adr/0007-single-writer-lock.md following the ADR format in docs/README.md (context, options considered with the reuse "
     "search performed, decision, consequences, status, date). Context: src/aop/store.py writes JSON documents atomically but assumes one "
     "process per organization root (ADR 0003 consequences). Options: an OS-level lock file (fcntl/msvcrt), a lock document with a lease, "
     "or deferring to a database backend. Do not modify any other file.",
     "docs/adr/0007-single-writer-lock.md exists with the five ADR sections; tests still pass", 2),
    ("T-002", "Organization.find_by_role(role) query",
     "In src/aop/organization.py add a method find_by_role(self, role: str) -> list[dict] on class Organization that returns the agent "
     "node dicts (from self.state.nodes) whose registry record (self.state.agents[node['agent_id']]) has role == role, sorted by node id, "
     "excluding retired nodes. Add tests/test_queries.py with two tests: a role present in the hierarchy built by tests/conftest.py "
     "build_hierarchy (both Developers found), and an unknown role (empty list). Do not modify any other file.",
     "tests/test_queries.py passes; the method has no side effects", 3),
    ("T-003", "Work.tasks_for_project(project_id) query",
     "In src/aop/work.py add a method tasks_for_project(self, project_id: str) -> list[Task] on class Work returning the Task objects of "
     "that project sorted by created_at. Add a test in tests/test_queries.py (create a project with two tasks; both returned in order). "
     "Do not modify any other file.",
     "tests pass; the method reads self._tasks() only", 4),
    ("T-004", "Document the kernel task template",
     "Create docs/task_template.md describing the fields of a kernel task (id, title, description, acceptance, priority) and the Definition "
     "of Ready of D3 §4.4 (objective, acceptance criteria, allowed paths, budget, risk class). Do not modify any other file.",
     "docs/task_template.md exists; tests still pass", 5),
]


def seed(workspace: Path, tasks, *, force: bool = False) -> dict:
    created, skipped = [], []
    existing = workspace.exists() and any((workspace / "tests").glob("test_*.py"))   # an existing project: keep its files
    for rel, content in ({} if existing and not force else WORKSPACE_SKELETON).items():
        dest = workspace / rel
        if dest.exists() and not force:
            skipped.append(rel); continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        created.append(rel)
    queued = []
    for tid, title, desc, acc, prio in FIRST_TASKS:
        try:
            tasks.find(tid)
            skipped.append(f"task {tid}")
        except FileNotFoundError:
            tasks.add(tid, title, desc, acc, prio)
            queued.append(tid)
    return {"created": created, "skipped": skipped, "queued": queued}
