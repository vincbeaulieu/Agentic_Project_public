"""Local model providers: LM Studio / OpenAI-compatible, Ollama native, Hugging Face local, the remote gate,
probing and the smoke test. A fake local HTTP server stands in for LM Studio and Ollama."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from kernel import KernelError
from kernel import localmodels
from kernel.model import HuggingFaceLocalModel, OllamaModel, OpenAICompatibleModel, build_model, is_local_endpoint


class FakeServer(BaseHTTPRequestHandler):
    seen = []

    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/v1/models":
            self._send({"models": [{"id": "google/gemma-4-12b-qat", "state": "loaded"}]})
        elif self.path.startswith("/api/v1/models/download/status/"):
            self._send({"job_id": self.path.rsplit("/", 1)[-1], "status": "completed", "progress": 1.0})
        elif self.path == "/v1/models":
            self._send({"data": [{"id": "qwen2.5-coder-7b-instruct"}, {"id": "llama-3.1-8b"}]})
        elif self.path == "/api/tags":
            self._send({"models": [{"name": "qwen2.5-coder:7b"}]})
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n)) if n else {}
        FakeServer.seen.append((self.path, body, dict(self.headers)))
        reply = json.dumps({"call": "abstain", "args": {"rationale": "smoke test"}})
        if self.path == "/v1/chat/completions":
            if body.get("model") in ("streamer", "reasoner-only") and body.get("stream"):
                self._send_stream(body.get("model")); return
            if body.get("model") == "no-json-mode" and "response_format" in body:
                self._send({"error": "response_format not supported"}, 400); return
            if body.get("model") == "no-system-role" and any(m["role"] == "system" for m in body["messages"]):
                self._send({"error": "System role not supported"}, 400); return
            self._send({"choices": [{"message": {"role": "assistant", "content": reply}}]})
        elif self.path == "/api/v1/chat":
            self._send({"model": body.get("model"), "output": {"content": reply}})
        elif self.path == "/api/v1/models/load":
            self._send({"model": body.get("model"), "status": "loaded"})
        elif self.path == "/api/v1/models/download":
            self._send({"job_id": "job-1", "model": body.get("model")})
        elif self.path == "/api/chat":
            self._send({"message": {"role": "assistant", "content": reply}, "done": True})
        else:
            self._send({"error": "not found"}, 404)

    def _send_stream(self, model):
        """SSE as LM Studio / llama.cpp emit it for reasoning models: reasoning_content deltas, then content deltas."""
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        def chunk(delta):
            self.wfile.write(("data: " + json.dumps({"choices": [{"index": 0, "delta": delta}]}) + "\n\n").encode()); self.wfile.flush()
        for i in range(40):
            chunk({"reasoning_content": f"think{i} "})
            time.sleep(0.01)
        if model == "streamer":
            for part in ('{"call": "abstain", ', '"args": {"rationale": "streamed"}}'):
                chunk({"content": part})
        self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()

    def log_message(self, *a):  # silence
        pass


@pytest.fixture(scope="module")
def server():
    srv = HTTPServer(("127.0.0.1", 0), FakeServer)
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_openai_compatible_lmstudio_style(server):
    m = build_model({"provider": "lmstudio", "base_url": server + "/v1", "model": "qwen2.5-coder-7b-instruct", "json_mode": True})
    assert isinstance(m, OpenAICompatibleModel)
    out = m.complete("sys", "user", max_output_chars=1000)
    assert json.loads(out)["call"] == "abstain"
    path, body, headers = FakeServer.seen[-1]
    assert path == "/v1/chat/completions" and body["response_format"] == {"type": "json_object"} and body["messages"][0]["role"] == "system"
    assert "Authorization" not in headers                      # no key configured -> no header
    assert m.list_models() == ["qwen2.5-coder-7b-instruct", "llama-3.1-8b"]


def test_api_key_comes_from_environment_only(server, monkeypatch):
    monkeypatch.setenv("SEED_PROPOSER_API_KEY", "sk-local-123")
    m = build_model({"provider": "openai_compatible", "base_url": server + "/v1", "model": "x", "api_key_env": "SEED_PROPOSER_API_KEY"})
    m.complete("s", "u", max_output_chars=100)
    assert FakeServer.seen[-1][2].get("Authorization") == "Bearer sk-local-123"
    assert "sk-local-123" not in m.name


def test_ollama_native(server):
    m = build_model({"provider": "ollama", "base_url": server, "model": "qwen2.5-coder:7b", "json_mode": True, "max_tokens": 512})
    assert isinstance(m, OllamaModel)
    out = m.complete("sys", "user", max_output_chars=1000)
    assert json.loads(out)["call"] == "abstain"
    path, body, _ = FakeServer.seen[-1]
    assert path == "/api/chat" and body["format"] == "json" and body["stream"] is False and body["options"]["num_predict"] == 512
    assert m.list_models() == ["qwen2.5-coder:7b"]


def test_huggingface_local_with_injected_pipeline():
    calls = []
    def factory(model_id):
        calls.append(model_id)
        def pipe(messages, **kw):
            assert messages[0]["role"] == "system"
            return [{"generated_text": json.dumps({"call": "abstain", "args": {"rationale": "hf"}})}]
        return pipe
    m = build_model({"provider": "huggingface_local", "model": "Qwen/Qwen2.5-Coder-1.5B-Instruct"}, pipeline_factory=factory)
    assert isinstance(m, HuggingFaceLocalModel)
    out = m.complete("s", "u", max_output_chars=500); m.complete("s", "u", max_output_chars=500)
    assert json.loads(out)["args"]["rationale"] == "hf" and calls == ["Qwen/Qwen2.5-Coder-1.5B-Instruct"]   # loaded once


def test_remote_endpoint_refused_unless_allowed():
    with pytest.raises(KernelError):
        build_model({"provider": "openai_compatible", "base_url": "https://api.example.com/v1", "model": "x"})
    with pytest.raises(KernelError):
        build_model({"provider": "huggingface_router", "model": "meta-llama/Llama-3.1-8B-Instruct"})
    m = build_model({"provider": "huggingface_router", "model": "meta-llama/Llama-3.1-8B-Instruct"}, allow_remote=True)
    assert m.base_url == "https://router.huggingface.co/v1" and m.api_key_env == "HF_TOKEN"
    assert is_local_endpoint("http://localhost:1234/v1") and is_local_endpoint("http://127.0.0.1:11434") and not is_local_endpoint("http://10.0.0.5:1234")


def test_unknown_provider_refused():
    with pytest.raises(KernelError):
        build_model({"provider": "magic", "model": "x"})


def test_smoke_test_reports_json_compliance(server):
    res = localmodels.smoke_test({"provider": "lmstudio", "base_url": server + "/v1", "model": "qwen2.5-coder-7b-instruct"})
    assert res["reachable"] and res["json_object"] and res["call_field_present"] and res["latency_s"] >= 0
    res2 = localmodels.smoke_test({"provider": "ollama", "base_url": "http://127.0.0.1:9", "model": "x"})
    assert not res2["reachable"] and res2["error"]


def test_probe_rows_and_snippet(monkeypatch):
    rows = localmodels.probe(timeout=0.2)
    assert {r["provider"] for r in rows} >= {"lmstudio", "ollama"} and all("reachable" in r for r in rows)
    snip = localmodels.snippet("proposer", "ollama", "qwen2.5-coder:7b")
    assert '[models.proposer]' in snip and 'provider = "ollama"' in snip and 'http://localhost:11434' in snip and "allow_remote" not in snip
    snip2 = localmodels.snippet("monitor", "huggingface_router", "meta-llama/Llama-3.1-8B-Instruct")
    assert "allow_remote_endpoints = true" in snip2 and 'api_key_env = "HF_TOKEN"' in snip2
    with pytest.raises(KernelError):
        localmodels.snippet("proposer", "dummy", "x")


def test_kernel_builds_police_model_from_constitution(kernel_root, server):
    c = (kernel_root / "constitution.toml").read_text()
    c = c.replace('[models.police]\n# Police LLM (behavioural review; flags only). Optional; leave "dummy" to disable.\nprovider = "dummy"\nbase_url = "http://localhost:11434"',
                  f'[models.police]\nprovider = "ollama"\nbase_url = "{server}"')
    (kernel_root / "constitution.toml").write_text(c)
    from kernel.loop import Kernel, Layout
    from kernel.model import DummyModel
    k = Kernel(Layout.at(kernel_root), proposer=DummyModel([]), monitor=DummyModel([]), install_signal_handlers=False)
    assert isinstance(k.police_model, OllamaModel)
    res = k.dispatch(k.ctx_police, "police_llm_review", {"monitored_agent": "proposer"})
    assert res.allowed and res.output["component"] == "police_llm"


def test_json_mode_falls_back_when_server_rejects_response_format(server):
    m = build_model({"provider": "lmstudio", "base_url": server + "/v1", "model": "no-json-mode", "json_mode": True})
    out = m.complete("s", "u", max_output_chars=500)
    assert json.loads(out)["call"] == "abstain"
    assert "response_format" not in FakeServer.seen[-1][1]      # second attempt went without it


def test_system_role_rejection_falls_back_to_merged_user_turn(server):
    m = build_model({"provider": "lmstudio", "base_url": server + "/v1", "model": "no-system-role", "json_mode": True})
    out = m.complete("SYS-TEXT", "USER-TEXT", max_output_chars=500)
    assert json.loads(out)["call"] == "abstain"
    msgs = FakeServer.seen[-1][1]["messages"]
    assert len(msgs) == 1 and msgs[0]["role"] == "user" and "SYS-TEXT" in msgs[0]["content"] and "USER-TEXT" in msgs[0]["content"]


def test_lmstudio_native_chat_models_load_download(server):
    from kernel.model import LMStudioNativeModel
    m = build_model({"provider": "lmstudio_native", "base_url": server, "model": "google/gemma-4-12b-qat", "json_mode": True})
    assert isinstance(m, LMStudioNativeModel)
    out = m.complete("sys", "user", max_output_chars=500)
    assert json.loads(out)["call"] == "abstain"
    path, body, _ = FakeServer.seen[-1]
    assert path == "/api/v1/chat" and body["stream"] is False and body["messages"][0]["role"] == "system"
    assert m.list_models() == ["google/gemma-4-12b-qat"]
    assert m.load()["status"] == "loaded" and m.download("x/y")["job_id"] == "job-1" and m.download_status("job-1")["status"] == "completed"
    # a /v1 base_url is normalised for the native provider
    m2 = build_model({"provider": "lmstudio_native", "base_url": server + "/v1", "model": "g"})
    assert m2.base_url == server


def test_first_text_accepts_common_shapes():
    from kernel.model import _first_text
    assert _first_text({"choices": [{"message": {"content": "a"}}]}) == "a"
    assert _first_text({"message": {"content": "b"}}) == "b"
    assert _first_text({"output": {"content": [{"type": "text", "text": "c1"}, {"type": "text", "text": "c2"}]}}) == "c1c2"
    assert _first_text({"response": "d"}) == "d" and _first_text({"weird": 1}) is None


def test_probe_includes_native_row_and_parses_flexible_lists(server, monkeypatch):
    from kernel import localmodels
    monkeypatch.setattr(localmodels, "PROBES", [("lmstudio_native", server, "/api/v1/models", "models", "id"), ("lmstudio", server + "/v1", "/models", "data", "id")])
    rows = localmodels.probe(timeout=2)
    assert rows[0]["reachable"] and rows[0]["models"] == ["google/gemma-4-12b-qat"] and rows[1]["models"][0] == "qwen2.5-coder-7b-instruct"


def test_streaming_assembles_content_and_reasoning_with_progress(server):
    from kernel.model import Progress
    m = build_model({"provider": "lmstudio", "base_url": server + "/v1", "model": "streamer", "json_mode": False})
    m.progress = Progress()
    out = m.complete("sys", "user", max_output_chars=1000)
    assert json.loads(out)["args"]["rationale"] == "streamed"
    snap = m.progress.snapshot()
    assert snap["reasoning_chars"] > 0 and "think39" in snap["reasoning"] and snap["content"] == out and snap["chunks"] == 42
    assert m.last_reasoning.startswith("think0")
    assert FakeServer.seen[-1][1]["stream"] is True


def test_reasoning_only_reply_is_empty_content_with_reasoning_kept(server):
    m = build_model({"provider": "lmstudio", "base_url": server + "/v1", "model": "reasoner-only"})
    out = m.complete("sys", "user", max_output_chars=1000)
    assert out == "" and "think39" in m.last_reasoning


def test_cancel_stops_the_stream(server):
    import threading
    from kernel.model import Cancelled, Progress
    m = build_model({"provider": "lmstudio", "base_url": server + "/v1", "model": "streamer"})
    m.progress = Progress()
    threading.Timer(0.05, m.progress.cancel.set).start()
    with pytest.raises(Cancelled):
        m.complete("sys", "user", max_output_chars=1000)
    assert 0 < m.progress.snapshot()["reasoning_chars"] < len("think0 " * 40) + 1


def test_extra_body_and_non_streaming_config(server):
    m = build_model({"provider": "lmstudio", "base_url": server + "/v1", "model": "qwen2.5-coder-7b-instruct", "stream": False,
                     "extra_body": {"reasoning_effort": "low"}, "max_wall_seconds": 60})
    m.complete("sys", "user", max_output_chars=100)
    body = FakeServer.seen[-1][1]
    assert body["reasoning_effort"] == "low" and "stream" not in body and m.max_wall == 60
