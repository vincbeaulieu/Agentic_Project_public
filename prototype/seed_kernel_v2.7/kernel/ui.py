"""Local control panel (kernel v2.3; v2.4 Tasks page; v2.5 assistant sidebar; v2.7 background jobs with live model progress): a minimal web UI served on 127.0.0.1 only.

Every action button is dispatched as the `human` principal through `Kernel.dispatch`, so the UI
adds no authority: it is a front end to the same functions as the CLI (R04 §4, D2 §64 "a GUI should
not bypass backend authorization"). Approve/reject and resume require the human to type the exact
phrase into the form; the server compares it byte-for-byte as the CLI does. Requests to the agent are
made as tasks (title, description, acceptance criteria) on the Tasks page: a task is the only channel
from the human to the proposer, so every directive is a recorded, reviewable file. The assistant sidebar (v2.5)
lets the human describe a request in free text; the assistant model returns a draft of the task fields, which only
pre-fills the New-task form. The assistant has no authority and queues nothing; the human submits. A per-process random
token is embedded in every form and checked on every POST (protection against cross-site requests
from other pages open in the browser). Standard library only.
"""
from __future__ import annotations

import html
import json
import secrets
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import Halted, KernelError
from .loop import Kernel
from .model import Progress

CSS = """
body{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f4f5f7;color:#1a1a1a}
header{background:#1f2937;color:#fff;padding:10px 18px;display:flex;gap:18px;align-items:center;flex-wrap:wrap}
header a{color:#cbd5e1;text-decoration:none;font-size:14px}header a:hover{color:#fff}
main{padding:18px;max-width:1100px;margin:auto}
.layout{display:flex;gap:16px;align-items:flex-start;max-width:1480px;margin:auto;padding:18px}.layout main{flex:1 1 640px;padding:0;margin:0;max-width:none;min-width:0}
aside{flex:0 0 360px;position:sticky;top:12px}.chat{max-height:52vh;overflow:auto;border:1px solid #e5e7eb;border-radius:6px;padding:8px;background:#fafafa;font-size:13px}
.msg{margin:0 0 8px;padding:6px 8px;border-radius:6px;white-space:pre-wrap}.msg.user{background:#dbeafe}.msg.assistant{background:#fff;border:1px solid #e5e7eb}.msg .who{font-size:11px;color:#6b7280;display:block}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:14px 16px;margin-bottom:14px}
.row{display:flex;gap:14px;flex-wrap:wrap}.row .card{flex:1 1 260px}
h1{font-size:20px;margin:0 0 10px}h2{font-size:16px;margin:0 0 8px}
pre{background:#0f172a;color:#e2e8f0;padding:10px;border-radius:6px;overflow:auto;font-size:12px;max-height:520px;white-space:pre-wrap}
button,input[type=submit]{background:#2563eb;color:#fff;border:0;border-radius:6px;padding:7px 12px;cursor:pointer;font-size:13px}
button.warn,input.warn{background:#b91c1c}button.grey,input.grey{background:#6b7280}
input[type=text],textarea,select{padding:6px;border:1px solid #cbd5e1;border-radius:6px;width:100%;box-sizing:border-box;font-size:13px;font-family:inherit}
textarea{min-height:90px}label{display:block;font-size:12px;color:#374151;margin:8px 0 2px}
.ok{color:#15803d}.bad{color:#b91c1c}.muted{color:#6b7280;font-size:12px}
table{border-collapse:collapse;width:100%;font-size:13px}td,th{border-bottom:1px solid #e5e7eb;padding:6px 4px;text-align:left;vertical-align:top}
.banner{background:#fef3c7;border:1px solid #f59e0b;padding:8px;border-radius:6px;margin-bottom:8px}
form.inline{display:inline}form.block{display:block;max-width:760px}
"""


def _esc(x: Any) -> str:
    return html.escape(str(x))


class Job:
    """One long-running model action (chat draft, proposer cycle, qualification, smoke test) executed in a background
    thread so the panel stays responsive and shows the model's reasoning as it streams (v2.7)."""

    def __init__(self, kind: str, label: str) -> None:
        self.kind, self.label = kind, label
        self.started = time.time()
        self.progress = Progress()
        self.done = False
        self.error = ""
        self.thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return not self.done


class ControlPanel:
    REFRESH_SECONDS = 3

    def __init__(self, kernel: Kernel, host: str = "127.0.0.1", port: int = 8765) -> None:
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise KernelError("the control panel binds to loopback only")
        self.k = kernel
        self.host, self.port = host, port
        self.token = secrets.token_urlsafe(24)
        self.lock = threading.Lock()
        self.last_message = ""
        self.last_output = ""
        self.chat: list[dict] = []          # assistant conversation for this panel process (also logged to state/assistant/chat.jsonl)
        self.draft: dict | None = None      # current draft of the New-task form
        self.job: Job | None = None         # the current or last background model job

    # ------------------------------------------------------------- background jobs (v2.7)
    def _job_panel(self) -> str:
        j = self.job
        if j is None:
            return ""
        snap = j.progress.snapshot()
        elapsed = snap["elapsed_s"] if not j.done else round((j.progress.finished or time.time()) - j.started, 1)
        state = "running" if j.running else ("cancelled" if snap["cancelled"] else ("failed" if j.error else "finished"))
        head = (f"<h2>Model job: {_esc(j.label)} <span class='{'ok' if j.running else 'muted'}'>{state}</span></h2>"
                f"<p class='muted'>elapsed {elapsed}s · reasoning {snap['reasoning_chars']} chars · answer {snap['content_chars']} chars · "
                f"{snap['chars_per_s']} chars/s · {snap['chunks']} chunks" + (f" · <span class='bad'>{_esc(j.error)}</span>" if j.error else "") + "</p>")
        if j.running:
            head += ("<p class='muted'>The page refreshes every 3 s while the model works. Cancel closes the connection; LM Studio then stops generating.</p>"
                     + self.form('/action/cancel_job', 'Cancel this model call', cls='warn'))
        else:
            head += self.form('/action/dismiss_job', 'Dismiss', cls='grey')
        reasoning = snap["reasoning"][-6000:]
        content = snap["content"][-3000:]
        body = head
        if reasoning:
            body += f"<h3 style='font-size:14px;margin:10px 0 4px'>Reasoning (what the model is thinking, live)</h3><pre style='max-height:300px'>{_esc(reasoning)}</pre>"
        if content:
            body += f"<h3 style='font-size:14px;margin:10px 0 4px'>Answer so far</h3><pre style='max-height:200px'>{_esc(content)}</pre>"
        if not reasoning and not content and j.running:
            body += "<p class='muted'>waiting for the first token (prompt processing)…</p>"
        return f"<div class='card' style='border-color:#2563eb'>{body}</div>"

    def _start_job(self, kind: str, label: str, model: Any, fn) -> None:
        if self.job is not None and self.job.running:
            self.last_message = f"a model job is already running ({self.job.label}); wait for it or cancel it"
            return
        job = Job(kind, label)
        if model is not None:
            try:
                model.progress = job.progress
            except AttributeError:
                pass
        panel = self

        def run() -> None:
            err = ""
            try:
                fn()
            except Halted as exc:
                err = f"HALTED: {exc}"; panel.last_message = err
            except (KernelError, ValueError, FileNotFoundError) as exc:
                err = f"refused: {exc}"; panel.last_message = err
            except Exception as exc:  # a crash in a job is reported, never silent
                err = f"{type(exc).__name__}: {exc}"; panel.last_message = f"job failed: {err}"
            finally:
                job.error = err
                job.progress.finish(err)
                job.done = True
                if model is not None:
                    try:
                        model.progress = None
                    except AttributeError:
                        pass

        job.thread = threading.Thread(target=run, daemon=True, name=f"aop-job-{kind}")
        self.job = job
        self.last_message = f"started: {label}"
        job.thread.start()

    def _job_chat(self, msg: str) -> None:
        k = self.k
        out = k.draft_task(msg, list(self.chat), self.draft)
        with self.lock:
            self.chat.append({"role": "user", "text": msg})
            self.chat.append({"role": "assistant", "text": out["reply"] or ("draft updated" if out["parsed"] else "no draft"), "questions": out["questions"]})
            if out["parsed"] and out["draft"].get("title"):
                self.draft = out["draft"]
            self.last_message = "assistant: draft updated — review the New-task form" if (out["parsed"] and out["draft"].get("title")) else "assistant answered without a usable draft"
            self.last_output = json.dumps({k2: v for k2, v in out.items() if k2 != "reasoning"}, indent=2, ensure_ascii=False)

    def _job_propose(self) -> None:
        k = self.k
        res = k.propose()
        with self.lock:
            self.last_message = "cycle done" if res is None else ("call allowed" if res.allowed else f"call denied: {res.authz.reason}")
            self.last_output = "nothing to do (no queued task, or parked)" if res is None else json.dumps({"authorization": res.authz.result, "reason": res.authz.reason, "detail": res.authz.detail, "output": res.output}, indent=2, default=str)

    def _job_qualify(self, model) -> None:
        from . import qualify
        k = self.k
        rep = qualify.run(k.layout.root, model, "proposer")
        k.audit.append("human", "qualification_run", "proposer", f"{rep['passed']}/{rep['total']}", model=rep["model"], report=rep["report_path"])
        with self.lock:
            self.last_message = f"qualification: {rep['passed']}/{rep['total']} scenarios passed"
            self.last_output = "\n".join(f"{'PASS' if r['passed'] else 'FAIL'}  {r['scenario']:24} {r['note']}  ({r['latency_s']}s)" for r in rep["results"]) + f"\nreport: {rep['report_path']}"

    def _job_models_test(self) -> None:
        from . import localmodels
        k = self.k
        cfg = k.c.section("models").get("proposer")
        out = localmodels.smoke_test(cfg, allow_remote=bool(k.c.section("models").get("allow_remote_endpoints", False)))
        with self.lock:
            self.last_message = "smoke test: " + ("ok" if out["reachable"] and out["json_object"] else "problem (see output)"); self.last_output = json.dumps(out, indent=2)

    # ------------------------------------------------------------- assistant sidebar
    def _assistant_panel(self) -> str:
        enabled = self.k.assistant_model is not None
        name = _esc(getattr(self.k.assistant_model, "name", "?")) if enabled else "disabled"
        msgs = "".join(f"<div class='msg {t['role']}'><span class='who'>{'you' if t['role'] == 'user' else 'assistant'}</span>{_esc(t['text'])}"
                       + ("".join(f"<br>• {_esc(q)}" for q in t.get("questions", [])) if t.get("questions") else "") + "</div>" for t in self.chat[-30:])
        if not msgs:
            msgs = "<p class='muted'>Describe what you want in plain words, e.g. “add a divide function to calc with tests”. The assistant turns it into a task draft (title, description, acceptance criteria) and fills the New-task form; you review and click <i>Queue this task</i>. It cannot queue, approve, run or change anything itself.</p>"
        draft_note = ("<p class='muted'>Draft ready in the <a href='/tasks'>New-task form</a>. Reply here to refine it, or edit the form directly.</p>" if self.draft else "")
        fields = '<textarea name="message" placeholder="your request, or an answer to the assistant&#39;s question" style="min-height:70px"></textarea>'
        form = self.form('/action/chat', 'Draft a task from this', fields, block=True) if enabled else "<p class='bad'>[models.assistant] provider is \"dummy\": assistant disabled.</p>"
        clear = self.form('/action/clear_chat', 'Clear conversation', cls='grey') if self.chat else ""
        return (f"<div class='card'><h2>Assistant <span class='muted'>drafts tasks · no authority · model: {name}</span></h2>"
                f"<div class='chat'>{msgs}</div>{draft_note}{form}<p style='margin-top:6px'>{clear}</p></div>")

    # ------------------------------------------------------------- pages
    def page(self, title: str, body: str) -> str:
        st = self.k.status()
        state = "HALTED" if st["halted"] else ("FROZEN" if st["frozen"] else "running")
        cls = "bad" if st["halted"] else ("muted" if st["frozen"] else "ok")
        nav = " ".join(f'<a href="{p}">{t}</a>' for p, t in (("/", "Dashboard"), ("/tasks", "Tasks"), ("/requests", "Requests"), ("/blockers", "Blockers"), ("/incidents", "Incidents"),
                                                           ("/models", "Models"), ("/audit", "Audit"), ("/help", "Help")))
        msg = f'<div class="banner">{_esc(self.last_message)}</div>' if self.last_message else ""
        refresh = f"<meta http-equiv='refresh' content='{self.REFRESH_SECONDS}'>" if (self.job and self.job.running) else ""
        body = self._job_panel() + body
        return (f"<!doctype html><html><head><meta charset='utf-8'>{refresh}<title>AOP kernel — {_esc(title)}</title><style>{CSS}</style></head><body>"
                f"<header><strong>AOP seed kernel</strong> <span class='{cls}'>{state}</span> {nav}</header>"
                f"<div class='layout'><main>{msg}{body}</main><aside>{self._assistant_panel()}</aside></div></body></html>")

    def form(self, action: str, label: str, fields: str = "", cls: str = "", block: bool = False) -> str:
        return (f'<form class="{"block" if block else "inline"}" method="post" action="{action}"><input type="hidden" name="token" value="{self.token}">{fields}'
                f'<input type="submit" class="{cls}" value="{_esc(label)}"></form>')

    def dashboard(self) -> str:
        st = self.k.status()
        pend = st["pending_approvals"]
        tasks = st["tasks"]
        body = f"""
<h1>Dashboard</h1>
<div class="row">
<div class="card"><h2>Tasks <a href="/tasks" style="font-size:12px;font-weight:normal">(new task / queue)</a></h2><table>{''.join(f'<tr><td>{k}</td><td>{v}</td></tr>' for k, v in tasks.items())}</table>
{self.form('/action/propose', 'Run one proposer cycle')} {self.form('/action/quickstart', 'Quickstart (seed workspace + first tasks)', cls='grey')}</div>
<div class="card"><h2>Awaiting your decision</h2>{'<p class="muted">none</p>' if not pend else '<ul>' + ''.join(f'<li><a href="/request?id={_esc(r)}">{_esc(r)}</a></li>' for r in pend) + '</ul>'}
<p class="muted">blockers: {len(st['blockers'])} · open incidents: {len(st['open_incidents'])}</p></div>
<div class="card"><h2>Controls</h2>
{self.form('/action/halt', 'HALT (stop everything)', cls='warn')} {self.form('/action/freeze', 'Freeze mutations', cls='grey')} {self.form('/action/unfreeze', 'Unfreeze', cls='grey')}
<p class="muted">Resume after a halt requires the phrase:</p>{self.form('/action/resume', 'Resume', '<input type="text" name="phrase" placeholder="' + _esc(self.k.c.resume_phrase) + '">')}</div>
<div class="card"><h2>Integrity</h2><p>audit: <span class="{'ok' if st['audit_ok'] else 'bad'}">{_esc(st['audit'])}</span><br>police: <span class="{'ok' if st['police_ok'] else 'bad'}">{_esc(st['police'])}</span>
<br>constitution v{_esc(st['constitution_version'])} {_esc(st['constitution_sha256'])}<br>permissions v{_esc(st['permissions_version'])} {_esc(st['permissions_sha256'])}
<br>proposer: {_esc(st['proposer'])}<br>model calls: {st['activity'].get('model_calls', 0)}</p></div>
</div>
<div class="card"><h2>Last action output</h2><pre>{_esc(self.last_output or '(nothing yet)')}</pre></div>
<div class="card"><h2>Today's report</h2><pre>{_esc(self._today_report())}</pre></div>"""
        return self.page("Dashboard", body)

    def tasks_page(self) -> str:
        groups = self.k.tasks.all()
        nid = self.k.tasks.next_id()
        d = self.draft or {}
        prio = int(d.get("priority", 5) or 5)
        fields = (f'<label>Id</label><input type="text" name="task_id" value="{_esc(nid)}">'
                  f'<label>Title (one line: what you want)</label><input type="text" name="title" value="{_esc(d.get("title", ""))}" placeholder="e.g. Add a divide(a, b) function to src/calc.py">'
                  '<label>Description (the directive the agent receives: which files, what behaviour, what not to touch)</label>'
                  f'<textarea name="description" placeholder="Create src/aop/util.py with ... Add tests/test_util.py covering ... Do not modify any other file.">{_esc(d.get("description", ""))}</textarea>'
                  '<label>Acceptance criteria (how you will judge it done; a task without them is not ready)</label>'
                  f'<input type="text" name="acceptance" value="{_esc(d.get("acceptance", ""))}" placeholder="e.g. tests pass; divide(-6, 3) == -2; ZeroDivisionError on b == 0">'
                  '<label>Priority (1 = first, 9 = last)</label><select name="priority">' + ''.join(f'<option{" selected" if i == prio else ""}>{i}</option>' for i in range(1, 10)) + '</select><p></p>'
                  + ('<p class="muted">Pre-filled by the assistant from your request; review every field before queuing.</p>' if self.draft else ''))
        body = f"""<h1>Tasks</h1>
<div class="card"><h2>New task (your request to the agent)</h2>
<p class="muted">The agent only receives tasks; it never sees free-form chat. Describe the change in the description, keep it inside the writable scope
(src/**, docs/**, tests/**, README.md of the workspace), and state the acceptance criteria. After queuing, click <i>Run one proposer cycle</i> on the Dashboard.
If the agent needs something, it answers with a blocker (Blockers page); if it proposes a change, it appears under Requests for your decision.</p>
{self.form('/action/add_task', 'Queue this task', fields, block=True)}</div>"""
        labels = {"queue": "Queued (waiting for a cycle)", "active": "Active (a request is awaiting your decision)", "blocked": "Blocked (agent asked for guidance; see Blockers)",
                  "parked": "Parked (attempt limit reached or agent abstained)", "done": "Done (applied, tests passed)"}
        for state in ("queue", "active", "blocked", "parked", "done"):
            items = groups.get(state, [])
            body += f"<div class='card'><h2>{labels[state]} <span class='muted'>{len(items)}</span></h2>"
            if not items:
                body += "<p class='muted'>none</p>"
            else:
                body += "<table><tr><th>id</th><th>prio</th><th>title</th><th>acceptance</th><th>attempts</th><th>last note</th><th></th></tr>"
                for t in items:
                    last = _esc(t.history[-1]["note"])[:160] if t.history else ""
                    act = self.form('/action/requeue', 'Return to queue', f'<input type="hidden" name="task_id" value="{_esc(t.id)}"><input type="text" name="guidance" placeholder="guidance to the agent (optional)">', cls='grey') if state == "parked" else ""
                    body += f"<tr><td>{_esc(t.id)}</td><td>{t.priority}</td><td>{_esc(t.title)}</td><td class='muted'>{_esc(t.acceptance)[:120]}</td><td>{t.attempts}</td><td class='muted'>{last}</td><td>{act}</td></tr>"
                body += "</table>"
            body += "</div>"
        return self.page("Tasks", body)

    def requests_page(self) -> str:
        pend = self.k.pending_requests()
        archived = sorted(p.name for p in (self.k.approvals_dir / "pending").glob("req-*.*.md"))[-20:]
        body = "<h1>Requests</h1><div class='card'><h2>Pending</h2>" + ("<p class='muted'>none</p>" if not pend else
               "<ul>" + "".join(f"<li><a href='/request?id={_esc(r)}'>{_esc(r)}</a></li>" for r in pend) + "</ul>") + "</div>"
        body += "<div class='card'><h2>Recent dispositions</h2><ul>" + "".join(f"<li class='muted'>{_esc(a)}</li>" for a in archived) + "</ul></div>"
        return self.page("Requests", body)

    def request_page(self, rid: str) -> str:
        try:
            packet = self.k.packet_text(rid)
        except FileNotFoundError:
            return self.page("Request", f"<h1>Request {_esc(rid)}</h1><p class='bad'>no pending packet with that id</p>")
        ap, rj = self.k.c.approval_phrase.format(request_id=rid), self.k.c.rejection_phrase.format(request_id=rid)
        body = f"""<h1>Request {_esc(rid)}</h1>
<div class="card"><h2>Decide</h2><p class="muted">Type the phrase exactly. Approve: <code>{_esc(ap)}</code> — Reject: <code>{_esc(rj)}</code></p>
{self.form('/action/decide', 'Record decision', f'<input type="hidden" name="request_id" value="{_esc(rid)}"><input type="text" name="phrase" placeholder="type the approval or rejection phrase">')}
<p style="margin-top:10px">{self.form('/action/apply', 'Apply (after approval): checkpoint → write → tests → checkpoint | rollback', f'<input type="hidden" name="request_id" value="{_esc(rid)}">')}</p></div>
<div class="card"><h2>Packet</h2><pre>{_esc(packet)}</pre></div>"""
        return self.page("Request", body)

    def blockers_page(self) -> str:
        items = sorted(p for p in self.k.blockers_dir.glob("*.md") if ".resolved." not in p.name)
        body = "<h1>Blockers (escalations awaiting your guidance)</h1>"
        if not items:
            body += "<p class='muted'>none</p>"
        for p in items:
            tid = p.stem
            body += f"""<div class="card"><h2>{_esc(tid)}</h2><pre>{_esc(p.read_text(encoding='utf-8'))}</pre>
{self.form('/action/unblock', 'Return task to queue with this guidance', f'<input type="hidden" name="task_id" value="{_esc(tid)}"><input type="text" name="guidance" placeholder="your guidance to the agent">')}</div>"""
        return self.page("Blockers", body)

    def incidents_page(self) -> str:
        items = sorted(self.k.incidents_dir.glob("*.md"))
        body = "<h1>Incidents</h1>"
        if not items:
            body += "<p class='muted'>none</p>"
        for p in items:
            text = p.read_text(encoding="utf-8")
            pending = "- Judgment: (unrecorded" in text
            body += f"<div class='card'><h2>{_esc(p.stem)} <span class='muted'>{'finding pending' if pending else 'finding recorded'}</span></h2><pre>{_esc(text)}</pre>"
            if pending:
                body += self.form('/action/finding', 'Record finding',
                                  f'<input type="hidden" name="incident_id" value="{_esc(p.stem)}"><select name="judgment"><option>reasonable</option><option>judgment_failure</option><option>undetermined</option></select> <input type="text" name="note" placeholder="note">')
            body += "</div>"
        return self.page("Incidents", body)

    def models_page(self) -> str:
        from . import localmodels
        rows = localmodels.probe(timeout=1.5)
        table = "".join(f"<tr><td>{_esc(r['provider'])}</td><td>{_esc(r['base_url'])}</td><td class='{'ok' if r['reachable'] else 'bad'}'>{'reachable' if r['reachable'] else 'not reachable'}</td><td>{_esc(', '.join(r['models'][:6]))}</td></tr>" for r in rows)
        cfg = self.k.c.section("models")
        conf = "".join(f"<tr><td>{p}</td><td>{_esc(cfg.get(p, {}).get('provider'))}</td><td>{_esc(cfg.get(p, {}).get('model'))}</td><td>{_esc(cfg.get(p, {}).get('base_url', '-'))}</td></tr>" for p in ("proposer", "monitor", "police"))
        body = f"""<h1>Models</h1><div class="card"><h2>Local servers</h2><table><tr><th>provider</th><th>base url</th><th>state</th><th>models</th></tr>{table}</table></div>
<div class="card"><h2>Configured (constitution.toml)</h2><table><tr><th>principal</th><th>provider</th><th>model</th><th>base url</th></tr>{conf}</table>
<p>{self.form('/action/models_test', 'Smoke-test proposer')} {self.form('/action/qualify', 'Qualify proposer (7 scenarios, one model call each)')}</p>
<p class="muted">To change the model: edit [models.proposer] in constitution.toml (the change is recorded by hash at the next start).</p></div>"""
        return self.page("Models", body)

    def audit_page(self) -> str:
        evs = list(self.k.audit.events())[-60:]
        rows = "".join(f"<tr><td>{e['seq']}</td><td>{time.strftime('%H:%M:%S', time.localtime(e['ts']))}</td><td>{_esc(e.get('agent_id'))}</td><td>{_esc(e.get('function_id') or e.get('action'))}</td><td>{_esc(e.get('authorization') or e.get('result'))}</td><td>{_esc(e.get('denial_reason') or '')}</td><td class='muted'>{_esc(e.get('resource_id', ''))[:60]}</td></tr>" for e in reversed(evs))
        pol = self.k.police.events()[-20:]
        prow = "".join(f"<tr><td>{p['seq']}</td><td>{_esc(p['monitored_agent'])}</td><td>{_esc(p['classification'])}</td><td>{_esc(p['severity'])}</td><td>{_esc(p['action'])}</td></tr>" for p in reversed(pol))
        body = f"<h1>Audit (last 60)</h1><div class='card'><table><tr><th>#</th><th>time</th><th>agent</th><th>function</th><th>result</th><th>denial</th><th>resource</th></tr>{rows}</table></div><h2>Police (last 20)</h2><div class='card'><table><tr><th>#</th><th>agent</th><th>classification</th><th>severity</th><th>action</th></tr>{prow}</table></div>"
        return self.page("Audit", body)

    def help_page(self) -> str:
        body = """<h1>How this works</h1><div class="card">
<p><b>Requesting something.</b> There is no chat channel to the model. You write a <i>task</i> on the Tasks page (title, description, acceptance criteria); that file is the directive the agent receives, together with the constitution summary and the rules. Keep requests inside the workspace's writable scope and give one testable outcome per task; if the agent finds the directive unclear, misleading or out of scope, it must answer with a blocker instead of guessing.</p>
<p><b>Assistant sidebar.</b> Type a request in plain words; the assistant model returns a draft of the task fields and fills the New-task form. Answer its questions to refine the draft. The assistant has no authority: it cannot queue, approve, run or read files; every call is audited (<code>task_drafted</code>) and logged under state/assistant/. You remain the author of the task you queue.</p>
<p><b>Model jobs and reasoning.</b> A model call (assistant draft, proposer cycle, qualification, smoke test) runs in the background; a blue card at the top shows elapsed time, the model's reasoning as it streams, the answer so far, and a Cancel button. Local reasoning models can think for minutes at a few tokens per second; the full reasoning and answer of every call is kept under <code>state/model_traces/</code>. If a call ends with reasoning but no answer, the model exhausted <code>max_tokens</code> while thinking: shorten the request, raise <code>max_tokens</code>, set <code>extra_body = { reasoning_effort = "low" }</code> in the model's constitution block, or use a non-reasoning model.</p>
<p><b>Cycle.</b> <i>Run one proposer cycle</i> sends the next queued task to the model. The model returns one function call. The kernel authorizes it (default deny), records it, and either creates a request for your decision, pauses the task with a blocker, or parks it.</p>
<p><b>Your decisions.</b> Open a request, read the packet (evidence, flags, full file contents), type the approval or rejection phrase, then click Apply. Apply takes a checkpoint, writes the files, runs the tests, and keeps or rolls back the change. Nothing is ever applied without your typed phrase.</p>
<p><b>Blockers</b> are questions from the agent; answer with guidance and the task returns to the queue. <b>Incidents</b> are opened automatically (rollback, blocked kernel change, misleading directive report, budget breaker); record a finding after reading the nine questions.</p>
<p><b>Stopping.</b> HALT stops every cycle before its next step; Resume needs the phrase. Freeze blocks apply/restore but allows reading.</p>
<p><b>Models.</b> Probe shows local servers; Smoke-test checks the configured model answers in the expected JSON format; Qualify runs seven behavioural scenarios and writes a report under state/qualification/.</p>
<p class="muted">Everything on this panel goes through the same authorization engine as the command line, as the human principal; the panel is served on 127.0.0.1 only.</p></div>"""
        return self.page("Help", body)

    def _today_report(self) -> str:
        p = self.k.layout.state / str(self.k.c.section("reporting")["report_dir"]) / f"{time.strftime('%Y-%m-%d')}.md"
        return p.read_text(encoding="utf-8")[-4000:] if p.exists() else "(no report yet today)"

    # ------------------------------------------------------------- actions
    def act(self, name: str, form: dict[str, str]) -> None:
        k = self.k
        try:
            if name == "cancel_job":
                if self.job is not None and self.job.running:
                    self.job.progress.cancel.set(); self.last_message = "cancel requested; the connection closes at the next chunk"
                else:
                    self.last_message = "no running job"
                return
            if name == "dismiss_job":
                if self.job is not None and not self.job.running:
                    self.job = None
                self.last_message = ""
                return
            if self.job is not None and self.job.running and name not in ("halt", "freeze"):
                self.last_message = f"a model job is running ({self.job.label}); wait for it or cancel it before other actions"
                return
            if name == "halt" and self.job is not None and self.job.running:
                self.job.progress.cancel.set()
            if name == "propose":
                self._start_job("propose", "proposer cycle", k.proposer, self._job_propose)
            elif name == "add_task":
                tid = (form.get("task_id") or k.tasks.next_id()).strip()
                title, desc, acc = form.get("title", "").strip(), form.get("description", "").strip(), form.get("acceptance", "").strip()
                if not title or not desc:
                    raise ValueError("a task needs a title and a description")
                if not acc:
                    raise ValueError("a task needs acceptance criteria (Definition of Ready); state how you will judge it done")
                t = k.tasks.add(tid, title, desc, acc, int(form.get("priority", "5") or 5))
                k.audit.append("human", "task_added", t.id, "ok", title=t.title, via="control_panel")
                self.last_message = f"queued {t.id}: {t.title}"; self.last_output = t.to_toml(); self.draft = None
            elif name == "chat":
                msg = form.get("message", "").strip()
                if not msg:
                    raise ValueError("empty message")
                if k.assistant_model is None:
                    raise KernelError("no assistant model configured")
                self._start_job("chat", "assistant draft", k.assistant_model, lambda: self._job_chat(msg))
            elif name == "clear_chat":
                self.chat = []; self.draft = None; self.last_message = "assistant conversation cleared"
            elif name == "requeue":
                t = k.unblock(form.get("task_id", ""), form.get("guidance", "") or "returned to queue from the control panel")
                self.last_message = f"{t.id} returned to the queue"
            elif name == "quickstart":
                from . import quickstart
                out = quickstart.seed(k.layout.workspace, k.tasks)
                k.audit.append("human", "quickstart", "workspace", "ok", created=out["created"], queued=out["queued"])
                self.last_message = f"quickstart: {len(out['created'])} files created, {len(out['queued'])} tasks queued"; self.last_output = json.dumps(out, indent=2)
            elif name == "decide":
                res = k.approve(form.get("request_id", ""), form.get("phrase", ""))
                self.last_message = ("decision recorded: " + str(res.output.get("decision"))) if res.allowed else f"refused: {res.authz.reason} — {res.authz.detail}"
                self.last_output = json.dumps(res.output or res.authz.__dict__, indent=2, default=str)
            elif name == "apply":
                res = k.apply(form.get("request_id", ""))
                self.last_message = ("applied, tests passed" if res.allowed and (res.output or {}).get("applied") else ("applied but tests failed: rolled back" if res.allowed else f"refused: {res.authz.reason} — {res.authz.detail}"))
                self.last_output = json.dumps(res.output or res.authz.__dict__, indent=2, default=str)
            elif name == "halt":
                k.halt.request_stop("halted from control panel"); self.last_message = "HALTED. Resume requires the phrase."
            elif name == "freeze":
                (k.layout.state / "FREEZE").write_text("frozen from control panel\n", encoding="utf-8"); self.last_message = "frozen"
            elif name == "unfreeze":
                f = k.layout.state / "FREEZE"
                if f.exists(): f.unlink()
                self.last_message = "unfrozen"
            elif name == "resume":
                ok = k.halt.resume(form.get("phrase", ""), k.c.resume_phrase)
                if ok: k.audit.append("human", "resume", "STOP", "ok")
                self.last_message = "resumed" if ok else "phrase mismatch; still halted"
            elif name == "unblock":
                t = k.unblock(form.get("task_id", ""), form.get("guidance", "")); self.last_message = f"{t.id} returned to the queue"
            elif name == "finding":
                k.record_finding(form.get("incident_id", ""), form.get("judgment", "undetermined"), form.get("note", "")); self.last_message = "finding recorded"
            elif name == "models_test":
                self._start_job("models_test", "smoke test of the proposer model", None, self._job_models_test)
            elif name == "qualify":
                from .model import build_model
                cfg = k.c.section("models").get("proposer")
                model = build_model(cfg, allow_remote=bool(k.c.section("models").get("allow_remote_endpoints", False)))
                self._start_job("qualify", "qualification (7 scenarios)", model, lambda: self._job_qualify(model))
            else:
                self.last_message = f"unknown action {name}"
        except Halted as exc:
            self.last_message = f"HALTED: {exc}"
        except FileExistsError as exc:
            self.last_message = f"refused: a task with id {exc} already exists"
        except (KernelError, ValueError, FileNotFoundError) as exc:
            self.last_message = f"refused: {exc}"

    # ------------------------------------------------------------- server
    def handler(self):
        panel = self

        class H(BaseHTTPRequestHandler):
            def _send(self, body: str, code: int = 200, ctype: str = "text/html; charset=utf-8") -> None:
                data = body.encode("utf-8")
                self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(data)

            def do_GET(self):
                url = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(url.query)
                with panel.lock:
                    try:
                        if url.path == "/": body = panel.dashboard()
                        elif url.path == "/tasks": body = panel.tasks_page()
                        elif url.path == "/requests": body = panel.requests_page()
                        elif url.path == "/request": body = panel.request_page(q.get("id", [""])[0])
                        elif url.path == "/blockers": body = panel.blockers_page()
                        elif url.path == "/incidents": body = panel.incidents_page()
                        elif url.path == "/models": body = panel.models_page()
                        elif url.path == "/audit": body = panel.audit_page()
                        elif url.path == "/help": body = panel.help_page()
                        elif url.path == "/status.json": self._send(json.dumps(panel.k.status(), default=str), ctype="application/json"); return
                        else: self._send("not found", 404, "text/plain"); return
                    except Exception as exc:  # render errors, never crash the panel
                        body = panel.page("Error", f"<pre>{_esc(type(exc).__name__ + ': ' + str(exc))}</pre>")
                self._send(body)

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                form = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8")).items()}
                if form.get("token") != panel.token:
                    self._send("forbidden: missing or invalid form token", 403, "text/plain"); return
                if not self.path.startswith("/action/"):
                    self._send("not found", 404, "text/plain"); return
                with panel.lock:
                    panel.act(self.path[len("/action/"):], form)
                back = "/request?id=" + urllib.parse.quote(form["request_id"]) if form.get("request_id") and self.path.endswith(("/decide",)) else ("/tasks" if self.path.endswith(("/add_task", "/requeue", "/chat", "/clear_chat")) else "/")
                self.send_response(303); self.send_header("Location", back); self.end_headers()

            def log_message(self, *a):  # keep the console quiet
                pass
        return H

    def serve(self, open_browser: bool = True) -> None:
        srv = ThreadingHTTPServer((self.host, self.port), self.handler())
        url = f"http://{self.host}:{self.port}/"
        print(f"control panel: {url}   (Ctrl-C to stop; the kernel state is in {self.k.layout.state})")
        if open_browser:
            try:
                import webbrowser
                webbrowser.open(url)
            except Exception:
                pass
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            srv.server_close()
