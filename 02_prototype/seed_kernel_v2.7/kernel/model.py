"""Model adapters. The kernel is model-agnostic.

A proposer returns a Proposal. A monitor returns a risk score in [0, 1] with
flags. Both are plain HTTP calls to an OpenAI-compatible endpoint, or the
offline DummyModel used in tests. Secrets are read from the environment only,
at call time, and are not logged.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from . import KernelError

STATUSES = ("proposal", "escalate", "abstain")

PROPOSAL_SCHEMA_HINT = """Respond with ONE JSON object and nothing else:
{
  "status": "proposal" | "escalate" | "abstain",
      // proposal : you are proposing file contents for review (authorized operation)
      // escalate : the task cannot be completed confidently within your authority without
      //            external input (missing information, conflicting requirements, an unexpected
      //            condition, or a consequential decision that requires review). The task is
      //            paused and recorded on the blocker list; nothing is changed.
      // abstain  : the task is outside your competence or should not be done as stated.
  "rationale": "...",               // what you changed (or why you escalated/abstained), in plain language
  "evidence": {                     // REQUIRED for status = "proposal" (evidentiary standard, R03)
      "verified_facts": ["..."],    // statements you verified against the workspace contents or the task text
      "observed": ["..."],          // what you directly observed (file contents, test names, structure)
      "sourced": [{"claim": "...", "source": "path, URL or document id"}],   // information from an identifiable source
      "derived": [{"conclusion": "...", "premises": ["..."]}],               // conclusions whose premises are listed above
      "hypotheses": ["..."],        // possible explanations or expectations that remain unverified
      "unknown": ["..."]            // information required but unavailable
  },
  "unresolved": ["..."],            // questions or decisions that remain open
  "considered_actions": ["..."],    // alternatives you considered, when useful to reviewers
  "blocker": {                      // required when status = "escalate"
      "category": "imprecise_directive" | "misleading_directive" | "conflicting_directives" |
                  "insufficient_information" | "unexpected_condition" | "high_stakes_decision" |
                  "protected_change" | "other",
      "nature": "...",              // what prevents confident completion
      "constraint": "...",          // the requirement, constraint, assumption or evidence involved
      "input_needed": "..."         // what external input or decision would resolve it
  },
  "risk_self_report": "low|medium|high",
  "confidence": 0.0,                // 0..1, estimated probability that the tests will pass
  "files": {"relative/path.py": "full new file content", ...},   // empty unless status = "proposal"
  "requests": ["..."]               // assistance, tools, information or training you need
}"""


@dataclass
class Proposal:
    status: str = "proposal"
    rationale: str = ""
    files: dict[str, str] = field(default_factory=dict)
    risk_self_report: str = "medium"
    confidence: float = 0.0
    facts: list[str] = field(default_factory=list)          # legacy alias of evidence["verified_facts"]
    assumptions: list[str] = field(default_factory=list)    # legacy alias of evidence["hypotheses"]
    evidence: dict[str, list] = field(default_factory=dict) # six categories (R03); empty dict = block absent
    unresolved: list[str] = field(default_factory=list)
    considered_actions: list[str] = field(default_factory=list)
    blocker: dict[str, str] = field(default_factory=dict)
    requests: list[str] = field(default_factory=list)
    raw: str = ""

    # Backward-compatible view used by policy and loop code.
    @property
    def abstain(self) -> bool:
        return self.status != "proposal"

    @property
    def abstain_reason(self) -> str:
        if self.status == "escalate":
            return self.blocker.get("nature", "") or self.rationale
        return self.rationale

    @classmethod
    def from_json_text(cls, text: str) -> "Proposal":
        obj = _extract_json(text)
        status = str(obj.get("status", "")).strip().lower()
        if not status:  # legacy shape: {"abstain": true/false}
            status = "abstain" if obj.get("abstain") else "proposal"
        if status not in STATUSES:
            raise KernelError(f"proposal.status must be one of {STATUSES}")
        files = obj.get("files") or {}
        if not isinstance(files, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in files.items()):
            raise KernelError("proposal.files must map string paths to string contents")
        blocker = obj.get("blocker") or {}
        if not isinstance(blocker, dict):
            blocker = {"nature": str(blocker)}
        if status == "escalate" and not (blocker.get("nature") or obj.get("rationale") or obj.get("abstain_reason")):
            raise KernelError("an escalation must state the nature of the blocker")
        rationale = str(obj.get("rationale") or obj.get("abstain_reason") or "")[:20000]

        def strlist(key: str, n: int = 20) -> list[str]:
            return [str(u)[:1000] for u in (obj.get(key) or [])][:n]

        evidence = parse_evidence(obj.get("evidence"))
        facts = strlist("facts") or [x for x in evidence.get("verified_facts", []) if isinstance(x, str)]
        assumptions = strlist("assumptions") or [x for x in evidence.get("hypotheses", []) if isinstance(x, str)]
        if not evidence and (facts or assumptions):   # legacy shape: map onto the six categories
            evidence = {"verified_facts": list(facts), "observed": [], "sourced": [], "derived": [], "hypotheses": list(assumptions), "unknown": []}

        return cls(
            status=status,
            rationale=rationale,
            files=files if status == "proposal" else {},
            risk_self_report=str(obj.get("risk_self_report", "medium")),
            confidence=float(obj.get("confidence", 0.0) or 0.0),
            facts=facts, assumptions=assumptions, evidence=evidence, unresolved=strlist("unresolved"),
            considered_actions=strlist("considered_actions"),
            blocker={k: str(v)[:2000] for k, v in blocker.items()},
            requests=strlist("requests"),
            raw=text,
        )


EVIDENCE_KEYS = ("verified_facts", "observed", "sourced", "derived", "hypotheses", "unknown")


def parse_evidence(raw) -> dict[str, list]:
    """Normalize the evidence block. Returns {} when absent; otherwise all six keys present.

    `sourced` items become {"claim", "source"} dicts (source may be ""); `derived` items become
    {"conclusion", "premises"} dicts (premises may be []). Other categories are lists of strings.
    """
    if not isinstance(raw, dict) or not raw:
        return {}
    out: dict[str, list] = {}
    for key in EVIDENCE_KEYS:
        items = raw.get(key) or []
        if not isinstance(items, list):
            items = [items]
        norm = []
        for it in items[:40]:
            if key == "sourced":
                if isinstance(it, dict):
                    norm.append({"claim": str(it.get("claim", ""))[:1000], "source": str(it.get("source", ""))[:500]})
                else:
                    norm.append({"claim": str(it)[:1000], "source": ""})
            elif key == "derived":
                if isinstance(it, dict):
                    prem = it.get("premises") or []
                    if not isinstance(prem, list):
                        prem = [prem]
                    norm.append({"conclusion": str(it.get("conclusion", ""))[:1000], "premises": [str(x)[:500] for x in prem[:20]]})
                else:
                    norm.append({"conclusion": str(it)[:1000], "premises": []})
            else:
                norm.append(str(it)[:1000])
        out[key] = norm
    return out


@dataclass
class MonitorVerdict:
    risk_score: float
    flags: list[str] = field(default_factory=list)
    summary: str = ""


import re as _re

_THINK_RE = _re.compile(r"<think>.*?</think>", _re.DOTALL | _re.IGNORECASE)
_FENCE_RE = _re.compile(r"```(?:json|JSON)?\s*(.*?)```", _re.DOTALL)


def clean_model_text(text: str) -> str:
    """Remove reasoning blocks (<think>…</think>) and prefer the content of a ```json fence."""
    text = _THINK_RE.sub("", text or "")
    m = _FENCE_RE.findall(text)
    if m:
        # take the last fenced block that contains an object
        for block in reversed(m):
            if "{" in block:
                return block.strip()
    return text.strip()


def _balanced_object(text: str) -> str | None:
    """Return the LAST top-level {...} object in text, using brace balancing that respects strings."""
    last = None
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "{":
            depth, j, in_str, esc = 0, i, False, False
            while j < n:
                ch = text[j]
                if in_str:
                    if esc: esc = False
                    elif ch == "\\": esc = True
                    elif ch == '"': in_str = False
                else:
                    if ch == '"': in_str = True
                    elif ch == "{": depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            last = text[i:j + 1]; i = j; break
                j += 1
        i += 1
    return last


def _extract_json(text: str) -> dict:
    text = clean_model_text(text)
    candidate = _balanced_object(text)
    if candidate is None:
        raise KernelError("model output contained no JSON object")
    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError:
        # second attempt: outermost braces (handles unbalanced braces inside strings)
        start, end = text.find("{"), text.rfind("}")
        try:
            obj = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise KernelError(f"model output is not valid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise KernelError("model output JSON is not an object")
    return obj


class ChatModel(Protocol):
    name: str
    def complete(self, system: str, user: str, *, max_output_chars: int) -> str: ...


class DummyModel:
    """Offline model for tests and dry runs. Returns scripted responses in order."""

    name = "dummy"

    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, *, max_output_chars: int) -> str:
        self.calls.append((system, user))
        if not self.responses:
            return json.dumps({"status": "abstain", "rationale": "dummy model has no scripted response"})
        return self.responses.pop(0)[:max_output_chars]


class Progress:
    """Live view of one model call (v2.7): reasoning and answer text as they stream, byte counts, elapsed time and a
    cancel flag. A caller attaches one to a model (`model.progress = Progress()`); adapters that stream append to it and
    stop when `cancel` is set (closing the connection makes LM Studio / llama.cpp stop generating)."""

    def __init__(self) -> None:
        import threading
        self.lock = threading.Lock()
        self.cancel = threading.Event()
        self.started = time.time()
        self.finished: float | None = None
        self.reasoning = ""
        self.content = ""
        self.chunks = 0
        self.error = ""
        self.note = ""

    def add(self, *, reasoning: str = "", content: str = "") -> None:
        with self.lock:
            self.reasoning += reasoning
            self.content += content
            self.chunks += 1

    def snapshot(self) -> dict:
        with self.lock:
            end = self.finished or time.time()
            elapsed = max(end - self.started, 1e-6)
            return {"elapsed_s": round(elapsed, 1), "reasoning_chars": len(self.reasoning), "content_chars": len(self.content),
                    "chunks": self.chunks, "chars_per_s": round((len(self.reasoning) + len(self.content)) / elapsed, 1),
                    "reasoning": self.reasoning, "content": self.content, "done": self.finished is not None,
                    "cancelled": self.cancel.is_set(), "error": self.error, "note": self.note}

    def finish(self, error: str = "") -> None:
        with self.lock:
            self.finished = time.time(); self.error = error


LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal")


def _host_of(base_url: str) -> str:
    from urllib.parse import urlparse
    return (urlparse(base_url).hostname or "").lower()


def is_local_endpoint(base_url: str) -> bool:
    return _host_of(base_url) in LOCAL_HOSTS


def _post_json(url: str, body: dict, headers: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (configured URL)
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise KernelError(f"model endpoint returned HTTP {exc.code}: {exc.read()[:300]!r}") from exc
    except urllib.error.URLError as exc:
        raise KernelError(f"model endpoint unreachable: {exc.reason}") from exc


class Cancelled(KernelError):
    """The human cancelled the model call from the control panel."""


def _post_stream(url: str, body: dict, headers: dict, idle_timeout: float, progress: "Progress | None", max_wall: float) -> dict:
    """POST with `stream: true`; consume server-sent events and assemble a chat-completions-shaped payload.
    Reasoning deltas (`reasoning_content` / `reasoning`, as LM Studio and llama.cpp emit them for reasoning models) are
    kept apart from the answer. The idle timeout applies between chunks; `max_wall` bounds the whole call."""
    body = dict(body); body["stream"] = True
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json", **headers}, method="POST")
    reasoning, content, started = [], [], time.time()
    try:
        with urllib.request.urlopen(req, timeout=idle_timeout) as resp:  # noqa: S310
            ctype = str(resp.headers.get("Content-Type", ""))
            if "text/event-stream" not in ctype:              # the server ignored `stream`: a plain JSON reply
                payload = json.loads(resp.read().decode("utf-8"))
                if progress is not None:
                    try:
                        m = payload["choices"][0]["message"]
                        progress.add(reasoning=str(m.get("reasoning_content") or ""), content=str(m.get("content") or ""))
                    except (KeyError, IndexError, TypeError):
                        pass
                payload["streamed"] = True
                return payload
            for raw in resp:
                if progress is not None and progress.cancel.is_set():
                    raise Cancelled("model call cancelled by the human")
                if max_wall and time.time() - started > max_wall:
                    raise KernelError(f"model call exceeded max_wall_seconds ({int(max_wall)})")
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                try:
                    delta = obj["choices"][0].get("delta") or obj["choices"][0].get("message") or {}
                except (KeyError, IndexError, TypeError):
                    continue
                r = delta.get("reasoning_content") or delta.get("reasoning") or ""
                c = delta.get("content") or ""
                if r:
                    reasoning.append(r)
                if c:
                    content.append(c)
                if progress is not None and (r or c):
                    progress.add(reasoning=r, content=c)
    except urllib.error.HTTPError as exc:
        raise KernelError(f"model endpoint returned HTTP {exc.code}: {exc.read()[:300]!r}") from exc
    except urllib.error.URLError as exc:
        raise KernelError(f"model endpoint unreachable: {exc.reason}") from exc
    except TimeoutError as exc:
        raise KernelError(f"model endpoint idle for more than {int(idle_timeout)} s") from exc
    return {"choices": [{"message": {"role": "assistant", "content": "".join(content), "reasoning_content": "".join(reasoning)}}], "streamed": True}


def _get_json(url: str, headers: dict | None = None, timeout: float = 5.0) -> dict:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


class OpenAICompatibleModel:
    """Client for /v1/chat/completions: LM Studio (:1234), Ollama (:11434/v1), llama.cpp server, vLLM,
    Hugging Face TGI / router (https://router.huggingface.co/v1), OpenAI. Keys come from the environment."""

    provider = "openai_compatible"

    def __init__(self, cfg: Mapping[str, Any]) -> None:
        self.base_url = str(cfg.get("base_url", "http://localhost:1234/v1")).rstrip("/")
        self.model = str(cfg["model"])
        self.api_key_env = str(cfg.get("api_key_env", ""))
        self.temperature = float(cfg.get("temperature", 0.2))
        self.max_tokens = int(cfg.get("max_tokens", 4000))
        self.json_mode = bool(cfg.get("json_mode", False))
        self.timeout = float(cfg.get("timeout_seconds", 300))          # non-stream: whole call; stream: idle time between chunks
        self.stream = bool(cfg.get("stream", True))
        self.max_wall = float(cfg.get("max_wall_seconds", 0) or 0)      # 0 = unbounded (the panel's Cancel button remains)
        self.extra_body = dict(cfg.get("extra_body", {}) or {})          # passed through, e.g. {"reasoning_effort": "low"}
        self.name = f"openai_compatible:{self.model}@{_host_of(self.base_url)}"
        self.progress: Progress | None = None
        self.last_reasoning = ""

    def _headers(self) -> dict:
        key = os.environ.get(self.api_key_env, "") if self.api_key_env else ""
        return {"Authorization": f"Bearer {key}"} if key else {}

    def complete(self, system: str, user: str, *, max_output_chars: int) -> str:
        body: dict[str, Any] = {"model": self.model, "temperature": self.temperature, "max_tokens": self.max_tokens,
                                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if self.json_mode:
            body["response_format"] = {"type": "json_object"}
        body.update(self.extra_body)
        payload = self._post_with_fallbacks(body, system, user)
        try:
            msg = payload["choices"][0]["message"]
            text = msg.get("content") or ""
            self.last_reasoning = str(msg.get("reasoning_content") or msg.get("reasoning") or "")
            if not text and self.last_reasoning:
                text = ""   # reasoning-only reply (budget spent thinking): the caller treats it as malformed and reports it
        except (KeyError, IndexError, TypeError) as exc:
            raise KernelError("unexpected response shape from model endpoint") from exc
        if self.progress is not None and not payload.get("streamed"):
            self.progress.add(reasoning=self.last_reasoning, content=str(text))
        return str(text)[:max_output_chars]

    def _post(self, url: str, body: dict) -> dict:
        if self.stream:
            return _post_stream(url, body, self._headers(), self.timeout, self.progress, self.max_wall)
        return _post_json(url, body, self._headers(), self.timeout)

    def _post_with_fallbacks(self, body: dict, system: str, user: str) -> dict:
        """Two documented fallbacks for local servers, each tried once on an HTTP 4xx:
        1. the server or chat template rejects `response_format` -> resend without it;
        2. the chat template rejects the `system` role (some Gemma templates) -> merge system into the user turn."""
        url = f"{self.base_url}/chat/completions"
        try:
            return self._post(url, body)
        except KernelError as exc:
            if "HTTP 4" not in str(exc):
                raise
            first_error = str(exc)
        if "response_format" in body:
            body = dict(body); body.pop("response_format", None)
            try:
                return self._post(url, body)
            except KernelError as exc:
                if "HTTP 4" not in str(exc):
                    raise
        merged = dict(body)
        merged["messages"] = [{"role": "user", "content": f"[SYSTEM INSTRUCTIONS]\n{system}\n\n[TASK]\n{user}"}]
        try:
            return self._post(url, merged)
        except KernelError as exc:
            raise KernelError(f"model endpoint rejected the request after fallbacks; first error: {first_error[:200]}") from exc

    def list_models(self) -> list[str]:
        payload = _get_json(f"{self.base_url}/models", self._headers())
        return [str(m.get("id")) for m in payload.get("data", [])]


def _first_text(payload: Any) -> str | None:
    """Locate assistant text in a response of unknown but conventional shape."""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        for path in (("choices", 0, "message", "content"), ("message", "content"), ("output", "content"), ("content",), ("response",), ("text",), ("result",)):
            cur: Any = payload
            ok = True
            for key in path:
                try:
                    cur = cur[key]
                except (KeyError, IndexError, TypeError):
                    ok = False; break
            if ok and isinstance(cur, str):
                return cur
            if ok and isinstance(cur, list):   # content parts: [{"type": "text", "text": "..."}]
                parts = [c.get("text", "") for c in cur if isinstance(c, dict)]
                if parts:
                    return "".join(parts)
    return None


class LMStudioNativeModel:
    """LM Studio native REST API (base_url http://127.0.0.1:1234): POST /api/v1/chat, GET /api/v1/models,
    POST /api/v1/models/load, POST /api/v1/models/download, GET /api/v1/models/download/status/<job>.

    The request body follows the chat-completions convention (model, messages, stream=false, temperature,
    max_tokens, optional response_format); the response text is located by `_first_text`, which accepts the
    common shapes. The OpenAI-compatible `lmstudio` provider (/v1/chat/completions) remains the default and is
    the path verified by the test suite; use `python -m kernel models test proposer` to confirm either."""

    provider = "lmstudio_native"

    def __init__(self, cfg: Mapping[str, Any]) -> None:
        self.base_url = str(cfg.get("base_url", "http://127.0.0.1:1234")).rstrip("/")
        if self.base_url.endswith("/v1"):
            self.base_url = self.base_url[:-3]
        self.model = str(cfg["model"])
        self.api_key_env = str(cfg.get("api_key_env", ""))
        self.temperature = float(cfg.get("temperature", 0.2))
        self.max_tokens = int(cfg.get("max_tokens", 4000))
        self.json_mode = bool(cfg.get("json_mode", False))
        self.timeout = float(cfg.get("timeout_seconds", 300))
        self.name = f"lmstudio_native:{self.model}@{_host_of(self.base_url)}"

    def _headers(self) -> dict:
        key = os.environ.get(self.api_key_env, "") if self.api_key_env else ""
        return {"Authorization": f"Bearer {key}"} if key else {}

    def complete(self, system: str, user: str, *, max_output_chars: int) -> str:
        body: dict[str, Any] = {"model": self.model, "stream": False, "temperature": self.temperature, "max_tokens": self.max_tokens,
                                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if self.json_mode:
            body["response_format"] = {"type": "json_object"}
        url = f"{self.base_url}/api/v1/chat"
        try:
            payload = _post_json(url, body, self._headers(), self.timeout)
        except KernelError as exc:
            if "HTTP 4" not in str(exc):
                raise
            body.pop("response_format", None)
            body["messages"] = [{"role": "user", "content": f"[SYSTEM INSTRUCTIONS]\n{system}\n\n[TASK]\n{user}"}]
            payload = _post_json(url, body, self._headers(), self.timeout)
        text = _first_text(payload)
        if text is None:
            raise KernelError(f"unexpected response shape from LM Studio native API: keys={list(payload)[:8] if isinstance(payload, dict) else type(payload).__name__}")
        return str(text)[:max_output_chars]

    def list_models(self) -> list[str]:
        payload = _get_json(f"{self.base_url}/api/v1/models", self._headers())
        items = payload.get("models") or payload.get("data") or (payload if isinstance(payload, list) else [])
        out = []
        for m in items:
            if isinstance(m, dict):
                out.append(str(m.get("id") or m.get("key") or m.get("model_key") or m.get("name") or m))
            else:
                out.append(str(m))
        return out

    def load(self, model_id: str | None = None) -> dict:
        return _post_json(f"{self.base_url}/api/v1/models/load", {"model": model_id or self.model}, self._headers(), self.timeout)

    def download(self, model_id: str) -> dict:
        return _post_json(f"{self.base_url}/api/v1/models/download", {"model": model_id}, self._headers(), self.timeout)

    def download_status(self, job_id: str) -> dict:
        return _get_json(f"{self.base_url}/api/v1/models/download/status/{job_id}", self._headers(), timeout=30)


class OllamaModel:
    """Ollama native API (/api/chat). Default base_url http://localhost:11434. Supports Ollama's JSON mode."""

    provider = "ollama"

    def __init__(self, cfg: Mapping[str, Any]) -> None:
        self.base_url = str(cfg.get("base_url", "http://localhost:11434")).rstrip("/")
        self.model = str(cfg["model"])
        self.temperature = float(cfg.get("temperature", 0.2))
        self.max_tokens = int(cfg.get("max_tokens", 4000))
        self.json_mode = bool(cfg.get("json_mode", False))
        self.timeout = float(cfg.get("timeout_seconds", 300))
        self.name = f"ollama:{self.model}@{_host_of(self.base_url)}"

    def complete(self, system: str, user: str, *, max_output_chars: int) -> str:
        body: dict[str, Any] = {"model": self.model, "stream": False,
                                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                                "options": {"temperature": self.temperature, "num_predict": self.max_tokens}}
        if self.json_mode:
            body["format"] = "json"
        payload = _post_json(f"{self.base_url}/api/chat", body, {}, self.timeout)
        try:
            text = payload["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise KernelError("unexpected response shape from Ollama") from exc
        return str(text)[:max_output_chars]

    def list_models(self) -> list[str]:
        payload = _get_json(f"{self.base_url}/api/tags")
        return [str(m.get("name")) for m in payload.get("models", [])]


class HuggingFaceLocalModel:
    """In-process generation with Hugging Face Transformers (optional dependency: transformers, torch).

    The model runs inside the kernel process on this machine; no network is used after the weights are
    cached. A `pipeline_factory` can be injected for tests. Chat templates are applied when the tokenizer
    provides one; otherwise a plain system/user concatenation is used.
    """

    provider = "huggingface_local"

    def __init__(self, cfg: Mapping[str, Any], pipeline_factory: Any = None) -> None:
        self.model = str(cfg["model"])                 # e.g. "Qwen/Qwen2.5-Coder-7B-Instruct" or a local path
        self.temperature = float(cfg.get("temperature", 0.2))
        self.max_tokens = int(cfg.get("max_tokens", 2000))
        self.device = str(cfg.get("device", "auto"))
        self.name = f"huggingface_local:{self.model}"
        self._factory = pipeline_factory
        self._pipe = None

    def _load(self):
        if self._pipe is not None:
            return self._pipe
        if self._factory is not None:
            self._pipe = self._factory(self.model)
            return self._pipe
        try:
            from transformers import pipeline  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise KernelError("huggingface_local requires `pip install transformers torch` (or accelerate); not installed") from exc
        kwargs = {"device_map": "auto"} if self.device == "auto" else {"device": self.device}
        self._pipe = pipeline("text-generation", model=self.model, **kwargs)
        return self._pipe

    def complete(self, system: str, user: str, *, max_output_chars: int) -> str:
        pipe = self._load()
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        out = pipe(messages, max_new_tokens=self.max_tokens, do_sample=self.temperature > 0, temperature=max(self.temperature, 1e-5), return_full_text=False)
        try:
            item = out[0]
            text = item["generated_text"]
            if isinstance(text, list):   # some pipelines return the chat list back
                text = text[-1].get("content", "")
        except (KeyError, IndexError, TypeError) as exc:
            raise KernelError("unexpected output shape from transformers pipeline") from exc
        return str(text)[:max_output_chars]

    def list_models(self) -> list[str]:
        return [self.model]


PROVIDERS = {
    "dummy": None,
    "openai_compatible": OpenAICompatibleModel,   # LM Studio, Ollama (/v1), llama.cpp, vLLM, HF TGI/router, OpenAI
    "lmstudio": OpenAICompatibleModel,            # alias: default base_url http://localhost:1234/v1 (OpenAI-compatible endpoint)
    "lmstudio_native": LMStudioNativeModel,       # LM Studio REST API: /api/v1/chat, /api/v1/models, /api/v1/models/load
    "ollama": OllamaModel,
    "huggingface_local": HuggingFaceLocalModel,
    "huggingface_router": OpenAICompatibleModel,  # alias: base_url https://router.huggingface.co/v1, api_key_env HF_TOKEN
}

ALIAS_DEFAULTS = {
    "lmstudio": {"base_url": "http://localhost:1234/v1"},
    "lmstudio_native": {"base_url": "http://127.0.0.1:1234"},
    "ollama": {"base_url": "http://localhost:11434"},
    "huggingface_router": {"base_url": "https://router.huggingface.co/v1", "api_key_env": "HF_TOKEN"},
}


def build_model(cfg: Mapping[str, Any], *, allow_remote: bool = False, pipeline_factory: Any = None) -> ChatModel:
    """Construct a model client. Remote endpoints are refused unless `allow_remote` is set by the
    constitution ([models] allow_remote_endpoints = true), so that project data stays on the machine by
    default (D3 R8; data classification decision in D3 §14)."""
    provider = str(cfg.get("provider", "dummy"))
    if provider == "dummy":
        return DummyModel()
    if provider not in PROVIDERS:
        raise KernelError(f"unknown model provider: {provider} (known: {', '.join(PROVIDERS)})")
    merged = dict(ALIAS_DEFAULTS.get(provider, {}))
    merged.update({k: v for k, v in cfg.items()})
    if provider == "huggingface_local":
        return HuggingFaceLocalModel(merged, pipeline_factory=pipeline_factory)
    if provider == "lmstudio_native":
        base_url = str(merged.get("base_url", ""))
        if not allow_remote and not is_local_endpoint(base_url):
            raise KernelError(f"endpoint {base_url!r} is not local and [models] allow_remote_endpoints is false")
        return LMStudioNativeModel(merged)
    base_url = str(merged.get("base_url", ""))
    if not allow_remote and not is_local_endpoint(base_url):
        raise KernelError(f"endpoint {base_url!r} is not local and [models] allow_remote_endpoints is false")
    return PROVIDERS[provider](merged)  # type: ignore[misc]
