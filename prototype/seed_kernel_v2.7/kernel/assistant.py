"""Task-drafting assistant (kernel v2.5): a model that helps the human write a task record.

The assistant has no authority and no function-call interface. It receives the human's free-text
request, the workspace tree and the writable scope, and returns a *draft* of the task fields (title,
description, acceptance criteria, priority) plus clarifying questions. Nothing is queued by the
assistant: the draft only pre-fills the New-task form, and the human reviews, edits and submits it.
Each call is recorded in the audit log (`task_drafted`, input and output hashes) and in
state/assistant/chat.jsonl; the counters are kept separate from the proposer's activity so the
proposer's refresher schedule is unaffected.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from . import KernelError
from .model import ChatModel, _extract_json

DRAFT_SYSTEM = """You are the task-drafting assistant of a human operator who supervises a governed software agent.
You have no authority: you cannot run anything, read files, approve anything, or queue tasks. Your only output is a
draft of a TASK RECORD that the operator will review, edit and then queue for the agent. The agent later receives
the task text as its directive, so the description must be precise, self-contained and free of assumptions.

A good task has:
- title: one line, imperative, specific.
- description: which files to create or change (paths relative to the workspace), the exact behaviour, what NOT to touch.
  One testable outcome per task. Do not invent files that are not in the workspace tree; if the request refers to
  something that does not exist, say so in the questions and draft the closest reasonable task.
- acceptance: how the operator will judge it done — concrete, checkable statements (tests pass; f(x) == y; file exists with sections A, B).
- priority: integer 1 (first) to 9 (last); default 5.
Stay inside the writable scope given below; changes outside it will be refused by the kernel.
If the request is too broad, split it: draft the first task and list the remaining ones in "reply".

Respond with ONE JSON object and nothing else:
{"reply": "<one or two sentences to the operator>",
 "draft": {"title": "...", "description": "...", "acceptance": "...", "priority": 5},
 "questions": ["<clarifying question>", ...]}
"""


def _h(x: Any) -> str:
    return hashlib.sha256(json.dumps(x, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


class TaskDrafter:
    def __init__(self, model: ChatModel, *, max_output_chars: int = 8000) -> None:
        self.model = model
        self.max_output_chars = max_output_chars
        self.name = getattr(model, "name", "?")

    def build_prompt(self, message: str, history: list[dict], current_draft: dict | None, tree: str, writable: list[str]) -> tuple[str, str]:
        lines = [f"WRITABLE SCOPE (globs, relative to the workspace): {', '.join(writable) or '(none)'}", "",
                 "WORKSPACE TREE:", tree or "(empty workspace)", ""]
        if history:
            lines.append("CONVERSATION SO FAR:")
            for turn in history[-12:]:
                lines.append(f"{turn['role'].upper()}: {str(turn['text'])[:2000]}")
            lines.append("")
        if current_draft:
            lines += ["CURRENT DRAFT (revise it according to the new message):", json.dumps(current_draft, ensure_ascii=False, indent=1), ""]
        lines += ["OPERATOR'S MESSAGE:", message.strip(), "", "Return the JSON object now."]
        return DRAFT_SYSTEM, "\n".join(lines)

    def draft(self, message: str, history: list[dict], current_draft: dict | None, tree: str, writable: list[str]) -> dict:
        if not message.strip():
            raise ValueError("empty message")
        system, user = self.build_prompt(message, history, current_draft, tree, writable)
        raw = self.model.complete(system, user, max_output_chars=self.max_output_chars)
        reasoning = str(getattr(self.model, "last_reasoning", "") or "")
        if not raw.strip() and reasoning:
            return {"reply": (f"(the model spent its whole output budget reasoning — {len(reasoning)} characters — and returned no answer. "
                              "Options: a shorter request, a larger max_tokens, a lower reasoning effort, or a non-reasoning model. The reasoning is in the trace.)"),
                    "draft": current_draft or {}, "questions": [], "raw": "", "reasoning": reasoning, "input_hash": _h(user), "output_hash": _h(raw), "parsed": False}
        try:
            obj = _extract_json(raw)
        except KernelError as exc:
            return {"reply": f"(the assistant's answer could not be parsed: {exc})", "draft": current_draft or {}, "questions": [],
                    "raw": raw[:2000], "reasoning": reasoning, "input_hash": _h(user), "output_hash": _h(raw), "parsed": False}
        d = obj.get("draft") if isinstance(obj.get("draft"), dict) else {}
        draft = {"title": str(d.get("title", "") or "").strip()[:200],
                 "description": str(d.get("description", "") or "").strip()[:8000],
                 "acceptance": str(d.get("acceptance", "") or "").strip()[:2000],
                 "priority": _prio(d.get("priority", 5))}
        qs = obj.get("questions") or []
        questions = [str(q)[:500] for q in qs if str(q).strip()][:5] if isinstance(qs, list) else []
        return {"reply": str(obj.get("reply", "") or "")[:2000], "draft": draft, "questions": questions,
                "raw": raw[:2000], "reasoning": reasoning, "input_hash": _h(user), "output_hash": _h(raw), "parsed": True}


def _prio(v: Any) -> int:
    try:
        return min(9, max(1, int(v)))
    except (TypeError, ValueError):
        return 5
