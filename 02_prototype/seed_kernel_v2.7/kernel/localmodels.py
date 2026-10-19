"""Local model operations: probe local servers, list models, smoke-test a configured principal's model,
and print configuration snippets. Used by `python -m kernel models ...` and `doctor`.

Nothing here changes the constitution: the human edits [models.*] by hand; `snippet` prints what to paste.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Mapping

from . import KernelError
from .model import ALIAS_DEFAULTS, PROVIDERS, build_model, is_local_endpoint

PROBES = [
    ("lmstudio", "http://localhost:1234/v1", "/models", "data", "id"),
    ("lmstudio_native", "http://127.0.0.1:1234", "/api/v1/models", "models", "id"),
    ("ollama", "http://localhost:11434", "/api/tags", "models", "name"),
    ("openai_compatible (llama.cpp / vLLM default)", "http://localhost:8000/v1", "/models", "data", "id"),
    ("openai_compatible (llama.cpp server default)", "http://localhost:8080/v1", "/models", "data", "id"),
]

SMOKE_SYSTEM = ("You are being tested for JSON compliance. Reply with ONE JSON object only: "
                '{"call": "abstain", "args": {"rationale": "smoke test"}}')


def probe(timeout: float = 2.0) -> list[dict]:
    """Detect local model servers on their default ports. Returns one row per probe."""
    rows = []
    for provider, base, path, key, field in PROBES:
        row = {"provider": provider, "base_url": base, "reachable": False, "models": []}
        try:
            req = urllib.request.Request(base + path, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (localhost only)
                payload = json.loads(resp.read().decode("utf-8"))
            row["reachable"] = True
            items = payload.get(key) if isinstance(payload, dict) else payload
            if items is None and isinstance(payload, dict):
                items = payload.get("data") or payload.get("models") or []
            row["models"] = [str((m.get(field) or m.get("key") or m.get("name")) if isinstance(m, dict) else m) for m in (items or [])][:50]
        except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            row["error"] = str(getattr(exc, "reason", exc))[:120]
        rows.append(row)
    return rows


def smoke_test(cfg: Mapping[str, Any], *, allow_remote: bool = False, max_output_chars: int = 2000) -> dict:
    """Send one fixed prompt to the configured model and report latency and JSON validity.

    This is a connectivity and format check, not a qualification (D3 §8.2)."""
    model = build_model(cfg, allow_remote=allow_remote)
    t0 = time.monotonic()
    try:
        raw = model.complete(SMOKE_SYSTEM, "Respond now.", max_output_chars=max_output_chars)
        ok = True; err = ""
    except KernelError as exc:
        raw, ok, err = "", False, str(exc)
    latency = time.monotonic() - t0
    parsed = None
    if ok:
        try:
            parsed = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        except (ValueError, json.JSONDecodeError):
            parsed = None
    return {"model": getattr(model, "name", "?"), "reachable": ok, "error": err, "latency_s": round(latency, 2),
            "json_object": isinstance(parsed, dict), "call_field_present": isinstance(parsed, dict) and "call" in parsed,
            "sample": raw[:200]}


def snippet(principal: str, provider: str, model: str, base_url: str | None = None) -> str:
    if provider not in PROVIDERS or provider == "dummy":
        raise KernelError(f"provider must be one of: {', '.join(p for p in PROVIDERS if p != 'dummy')}")
    base = base_url or ALIAS_DEFAULTS.get(provider, {}).get("base_url", "http://localhost:1234/v1")
    lines = [f"[models.{principal}]", f'provider = "{provider}"']
    if provider != "huggingface_local":
        lines.append(f'base_url = "{base}"')
    lines.append(f'model = "{model}"')
    if provider == "huggingface_router":
        lines.append('api_key_env = "HF_TOKEN"')
    lines += ["temperature = 0.2", "max_tokens = 8000", "json_mode = true"]
    remote_note = "" if provider == "huggingface_local" or is_local_endpoint(base) else "\n# remote endpoint: also set allow_remote_endpoints = true under [models] (privacy decision, D3 §14)"
    return "\n".join(lines) + remote_note + "\n"


def load_model(cfg: Mapping[str, Any], model_id: str | None = None, *, allow_remote: bool = False) -> dict:
    """Ask LM Studio (native API) to load a model into memory."""
    from .model import LMStudioNativeModel
    m = build_model(dict(cfg, provider="lmstudio_native"), allow_remote=allow_remote)
    assert isinstance(m, LMStudioNativeModel)
    return m.load(model_id)


def download_model(cfg: Mapping[str, Any], model_id: str, *, allow_remote: bool = False) -> dict:
    from .model import LMStudioNativeModel
    m = build_model(dict(cfg, provider="lmstudio_native", model=model_id), allow_remote=allow_remote)
    assert isinstance(m, LMStudioNativeModel)
    return m.download(model_id)


def download_status(cfg: Mapping[str, Any], job_id: str, *, allow_remote: bool = False) -> dict:
    from .model import LMStudioNativeModel
    m = build_model(dict(cfg, provider="lmstudio_native"), allow_remote=allow_remote)
    assert isinstance(m, LMStudioNativeModel)
    return m.download_status(job_id)
