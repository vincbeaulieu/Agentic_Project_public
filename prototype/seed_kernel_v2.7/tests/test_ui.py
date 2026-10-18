"""Control panel: loopback only, form token required, every action goes through dispatch as the human."""
import json
import threading
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from kernel import KernelError
from kernel.loop import Kernel, Layout
from kernel.model import DummyModel
from kernel.ui import ControlPanel

from conftest import GOOD_PATCH, patch_call


@pytest.fixture
def panel(kernel_root):
    k = Kernel(Layout.at(kernel_root), proposer=DummyModel([patch_call(), patch_call()]), monitor=DummyModel([]), install_signal_handlers=False)
    p = ControlPanel(k, port=0)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), p.handler())
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    p.base = f"http://127.0.0.1:{srv.server_port}"
    yield p
    srv.shutdown()


def get(p, path):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(p.base + path, timeout=10) as r:
        return r.status, r.read().decode()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post(p, path, **form):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(p.base + path, data=data, method="POST")
    try:
        with opener.open(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def wait(p, timeout=20):
    """Background model jobs (v2.7): wait for the current job to finish."""
    if p.job is not None and p.job.thread is not None:
        p.job.thread.join(timeout)
    assert p.job is None or not p.job.running


def test_panel_refuses_non_loopback_binding(kernel_root):
    k = Kernel(Layout.at(kernel_root), proposer=DummyModel([]), monitor=DummyModel([]), install_signal_handlers=False)
    with pytest.raises(KernelError):
        ControlPanel(k, host="0.0.0.0")


def test_pages_render(panel):
    for path in ("/", "/tasks", "/requests", "/blockers", "/incidents", "/audit", "/help", "/status.json"):
        status, body = get(panel, path)
        assert status == 200 and body, path
    assert "AOP seed kernel" in get(panel, "/")[1]


def test_post_without_token_is_forbidden_and_has_no_effect(panel):
    panel.k.tasks.add("t1", "add mul", "add mul")
    assert post(panel, "/action/propose") == 403
    assert panel.k.pending_requests() == []


def test_full_cycle_through_panel(panel):
    k = panel.k
    k.tasks.add("t1", "add mul", "add mul")
    assert post(panel, "/action/propose", token=panel.token) == 303
    wait(panel)
    rid = k.pending_requests()[0]
    status, body = get(panel, f"/request?id={rid}")
    assert "Request hash" in body and "Files to be written" in body
    # wrong phrase -> refused (through the engine), nothing applied
    assert post(panel, "/action/decide", token=panel.token, request_id=rid, phrase="approve please") == 303
    assert "refused" in panel.last_message
    assert post(panel, "/action/apply", token=panel.token, request_id=rid) == 303
    assert "refused" in panel.last_message and "mul" not in (k.layout.workspace / "src" / "calc.py").read_text()
    # exact phrase -> recorded; apply -> tests pass
    assert post(panel, "/action/decide", token=panel.token, request_id=rid, phrase=k.c.approval_phrase.format(request_id=rid)) == 303
    assert "decision recorded: approved" in panel.last_message
    assert post(panel, "/action/apply", token=panel.token, request_id=rid) == 303
    assert "applied, tests passed" in panel.last_message and "mul" in (k.layout.workspace / "src" / "calc.py").read_text()
    evs = [e for e in k.audit.events() if e.get("function_id") in ("record_approval", "apply_approved_request")]
    assert all(e["agent_id"] == "human" for e in evs) and any(e["authorization"] == "DENY" for e in evs)


def test_halt_and_resume_through_panel(panel):
    assert post(panel, "/action/halt", token=panel.token) == 303
    assert panel.k.halt.stopped
    assert post(panel, "/action/resume", token=panel.token, phrase="nope") == 303 and panel.k.halt.stopped
    assert post(panel, "/action/resume", token=panel.token, phrase=panel.k.c.resume_phrase) == 303 and not panel.k.halt.stopped


def test_task_form_queues_task_and_audits(panel):
    k = panel.k
    st = post(panel, "/action/add_task", token=panel.token, task_id="", title="Add divide", description="Add divide(a, b) to src/calc.py.",
              acceptance="tests pass; divide(-6, 3) == -2", priority="3")
    assert st == 303
    t = k.tasks.find("T-001")
    assert t.title == "Add divide" and t.priority == 3 and t.path.parent == k.tasks.queue
    assert k.tasks.next_id() == "T-002"
    ev = [e for e in k.audit.events() if e.get("action") == "task_added" or e.get("function_id") == "task_added"]
    assert ev and ev[-1]["details"].get("via") == "control_panel"
    status, body = get(panel, "/tasks")
    assert "Add divide" in body and "T-001" in body


def test_task_form_requires_acceptance_and_token(panel):
    k = panel.k
    assert post(panel, "/action/add_task", token="wrong", task_id="T-009", title="x", description="y", acceptance="z") == 403
    assert post(panel, "/action/add_task", token=panel.token, task_id="T-009", title="x", description="y", acceptance="") == 303
    assert "refused" in panel.last_message and "acceptance" in panel.last_message
    with pytest.raises(FileNotFoundError):
        k.tasks.find("T-009")
    post(panel, "/action/add_task", token=panel.token, task_id="T-009", title="x", description="y", acceptance="z")
    post(panel, "/action/add_task", token=panel.token, task_id="T-009", title="x", description="y", acceptance="z")
    assert "already exists" in panel.last_message


def test_parked_task_can_be_requeued_from_panel(panel):
    k = panel.k
    t = k.tasks.add("T-010", "t", "d", "a")
    k.tasks.move(t, k.tasks.parked, "abstained")
    assert post(panel, "/action/requeue", token=panel.token, task_id="T-010", guidance="try again with the spec in docs/") == 303
    t2 = k.tasks.find("T-010")
    assert t2.path.parent == k.tasks.queue and t2.history[-1]["note"].startswith("GUIDANCE:")


DRAFT_JSON = json.dumps({"reply": "Drafted; one question.", "draft": {"title": "Add divide to calc", "description": "Add divide(a, b) to src/calc.py; add tests/test_calc.py cases. Do not modify other files.",
                         "acceptance": "tests pass; divide(-6, 3) == -2", "priority": 3}, "questions": ["Raise ZeroDivisionError on b == 0?"]})


@pytest.fixture
def apanel(kernel_root):
    k = Kernel(Layout.at(kernel_root), proposer=DummyModel([]), monitor=DummyModel([]), assistant=DummyModel([DRAFT_JSON, "no json here"]), install_signal_handlers=False)
    p = ControlPanel(k, port=0)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), p.handler())
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    p.base = f"http://127.0.0.1:{srv.server_port}"
    yield p
    srv.shutdown()


def test_assistant_drafts_and_prefills_form_without_queuing(apanel):
    k = apanel.k
    assert post(apanel, "/action/chat", token=apanel.token, message="add a divide function to calc with tests") == 303
    wait(apanel)
    status, body = get(apanel, "/")
    assert "Model job: assistant draft" in body and "finished" in body            # job card with outcome
    assert apanel.draft["title"] == "Add divide to calc" and apanel.draft["priority"] == 3
    status, body = get(apanel, "/tasks")
    assert 'value="Add divide to calc"' in body and "Raise ZeroDivisionError" in body and "Pre-filled by the assistant" in body
    assert k.tasks.counts()["queue"] == 0                                   # nothing queued by the assistant
    ev = [e for e in k.audit.events() if e.get("action") == "task_drafted"]
    assert len(ev) == 1 and ev[0]["result"] == "ok" and ev[0]["input_hash"] and ev[0]["output_hash"]
    assert (k.layout.state / "assistant" / "chat.jsonl").exists()
    assert k._activity().get("draft_calls") == 1 and k._activity()["model_calls"] == 0   # proposer counters untouched
    # queue it through the form, as the human
    d = apanel.draft
    assert post(apanel, "/action/add_task", token=apanel.token, task_id="", title=d["title"], description=d["description"], acceptance=d["acceptance"], priority=str(d["priority"])) == 303
    assert k.tasks.counts()["queue"] == 1 and apanel.draft is None
    # unparsable second answer: recorded, draft unchanged, nothing queued
    post(apanel, "/action/chat", token=apanel.token, message="and also multiply"); wait(apanel)
    assert "without a usable draft" in apanel.last_message and k.tasks.counts()["queue"] == 1
    assert [e for e in k.audit.events() if e.get("action") == "task_drafted"][-1]["result"] == "unparsed"


def test_assistant_refused_while_halted_and_without_token(apanel):
    k = apanel.k
    assert post(apanel, "/action/chat", token="wrong", message="x") == 403
    k.halt.request_stop("test")
    post(apanel, "/action/chat", token=apanel.token, message="add a function"); wait(apanel)
    assert apanel.last_message.startswith("HALTED") and apanel.draft is None
    assert not [e for e in k.audit.events() if e.get("action") == "task_drafted"]


def test_assistant_disabled_by_constitution(kernel_root):
    c = kernel_root / "constitution.toml"
    c.write_text(c.read_text(encoding="utf-8").replace('provider = "proposer"\n', 'provider = "dummy"\n'), encoding="utf-8")
    k = Kernel(Layout.at(kernel_root), proposer=DummyModel([]), monitor=DummyModel([]), install_signal_handlers=False)
    assert k.assistant_model is None
    with pytest.raises(KernelError):
        k.draft_task("x", [], None)


class SlowModel:
    """Streams reasoning slowly through Progress so the panel can be observed mid-call; honours cancel."""
    name = "slow"

    def __init__(self):
        self.progress = None
        self.last_reasoning = ""

    def complete(self, system, user, *, max_output_chars):
        from kernel.model import Cancelled
        import time as _t
        for i in range(200):
            if self.progress is not None and self.progress.cancel.is_set():
                raise Cancelled("cancelled")
            if self.progress is not None:
                self.progress.add(reasoning=f"step {i} ")
            _t.sleep(0.02)
        return json.dumps({"reply": "ok", "draft": {"title": "t", "description": "d", "acceptance": "a", "priority": 5}, "questions": []})


def test_job_shows_live_reasoning_blocks_other_actions_and_cancels(kernel_root):
    import time as _t
    k = Kernel(Layout.at(kernel_root), proposer=DummyModel([]), monitor=DummyModel([]), assistant=SlowModel(), install_signal_handlers=False)
    p = ControlPanel(k, port=0)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), p.handler())
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    p.base = f"http://127.0.0.1:{srv.server_port}"
    try:
        assert post(p, "/action/chat", token=p.token, message="make a calculator") == 303
        _t.sleep(0.3)
        status, body = get(p, "/")
        assert "Model job: assistant draft" in body and "running" in body and "step " in body and "http-equiv='refresh'" in body
        assert "Cancel this model call" in body
        # other mutations are refused while the job runs
        post(p, "/action/add_task", token=p.token, task_id="T-001", title="x", description="y", acceptance="z")
        assert "a model job is running" in p.last_message and k.tasks.counts()["queue"] == 0
        assert post(p, "/action/cancel_job", token=p.token) == 303
        wait(p)
        assert not p.job.running and p.job.progress.snapshot()["cancelled"] and "refused: cancelled" in p.last_message
        status, body = get(p, "/")
        assert "cancelled" in body and "Dismiss" in body
        assert p.draft is None                                   # a cancelled draft changes nothing
        assert not [e for e in k.audit.events() if e.get("action") == "task_drafted"]
        post(p, "/action/dismiss_job", token=p.token)
        assert p.job is None
    finally:
        srv.shutdown()
