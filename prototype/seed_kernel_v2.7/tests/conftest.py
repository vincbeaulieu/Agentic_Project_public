import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

GOOD_EVIDENCE = {
    "verified_facts": ["src/calc.py defines add(a, b) returning a + b"],
    "observed": ["tests/test_calc.py contains test_add"],
    "sourced": [{"claim": "task requests a mul function", "source": "task t1 description"}],
    "derived": [{"conclusion": "adding mul does not change add", "premises": ["mul is a new function", "add is unchanged"]}],
    "hypotheses": [],
    "unknown": [],
}
GOOD_PATCH = {"src/calc.py": "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n"}
BAD_PATCH = {"src/calc.py": "def add(a, b):\n    return a - b\n"}


@pytest.fixture
def kernel_root(tmp_path: Path) -> Path:
    text = (ROOT / "constitution.toml").read_text(encoding="utf-8")
    text = "\n".join(('workspace_dir = "workspace"' if l.startswith("workspace_dir = ") else l) for l in text.splitlines()) + "\n"
    (tmp_path / "constitution.toml").write_text(text, encoding="utf-8")   # tests use a workspace inside the temp root
    shutil.copy(ROOT / "permissions.toml", tmp_path / "permissions.toml")
    ws = tmp_path / "workspace"
    (ws / "src").mkdir(parents=True); (ws / "tests").mkdir()
    (ws / "src" / "__init__.py").write_text("", encoding="utf-8")
    (ws / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (ws / "tests" / "test_calc.py").write_text(
        "import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))\n"
        "from src.calc import add\n\ndef test_add():\n    assert add(1, 2) == 3\n", encoding="utf-8")
    return tmp_path


def call_json(call: str, **args) -> str:
    return json.dumps({"call": call, "args": args})


def patch_call(files=None, evidence=None, **extra) -> str:
    args = {"files": files if files is not None else GOOD_PATCH, "rationale": "add mul", "risk_self_report": "low", "confidence": 0.9}
    if evidence is not None:
        args["evidence"] = evidence
    elif evidence is None and "no_evidence" not in extra:
        args["evidence"] = GOOD_EVIDENCE
    extra.pop("no_evidence", None)
    args.update(extra)
    return call_json("propose_patch", **args)


def blocker_call(category="insufficient_information", nature="which module?", **extra) -> str:
    return call_json("report_blocker", blocker={"category": category, "nature": nature, "constraint": "c", "input_needed": "n"},
                     evidence={"verified_facts": ["x"], "observed": [], "sourced": [], "derived": [], "hypotheses": [], "unknown": ["y"]}, **extra)
