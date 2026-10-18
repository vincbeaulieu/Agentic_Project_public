"""Command-line interface (kernel v2.0). Human operations are dispatched as the `human` principal
through the same authorization engine as agent calls; every command that touches protected state
is therefore audited and default-deny.

    python -m kernel init | status | verify-audit | checkpoints | restore CID
    python -m kernel add-task ID "title" "description" ["acceptance"] [--priority N]
    python -m kernel propose                     one proposer cycle (model -> one function call -> dispatch)
    python -m kernel review REQ | approve REQ | reject REQ | apply REQ
    python -m kernel halt ["reason"] | freeze | unfreeze | resume
    python -m kernel blockers | unblock TASK "guidance" | incidents | finding INC <judgment> "note"
    python -m kernel twe TWE_ID                  entries of a TWE (via read_twe, as human)
    python -m kernel police                      police events
    python -m kernel profile [PRINCIPAL]         authorization profile of a principal
    python -m kernel models probe                detect LM Studio / Ollama / llama.cpp / vLLM servers on default ports
    python -m kernel models test [PRINCIPAL]     smoke-test the configured model of proposer|monitor|police
    python -m kernel models snippet PRINCIPAL PROVIDER MODEL [--base-url URL]   print a [models.*] block to paste
    python -m kernel models load [MODEL] | download MODEL | status JOB   LM Studio native API (/api/v1/models/...)
    python -m kernel serve [--interval S] [--max-cycles N]   continuous operation: propose until STOP/FREEZE or limit
    python -m kernel doctor                      environment, models, isolation and test-suite checks
    python -m kernel qualify [PRINCIPAL]         run the behavioural qualification scenarios against the configured model
    python -m kernel quickstart                  seed the workspace skeleton and the first self-build tasks (T-001..T-004)
    python -m kernel ui [--port 8765] [--no-browser]   local control panel on 127.0.0.1 (dashboard, requests, blockers, incidents, models, audit)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import Halted, KernelError
from .loop import Kernel, Layout


def _kernel(root: Path) -> Kernel:
    return Kernel(Layout.at(root))


def _print_result(res, ok_msg: str) -> int:
    if res.allowed:
        print(ok_msg if not isinstance(res.output, (dict, list)) else json.dumps(res.output, indent=2, default=str)); return 0
    print(f"DENIED ({res.authz.reason}): {res.authz.detail}" if not res.error else f"ERROR: {res.error}", file=sys.stderr); return 4


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="kernel", description="seed kernel v2.0 - default-deny, human-governed self-build loop")
    ap.add_argument("--root", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("init", "status", "propose", "verify-audit", "checkpoints", "freeze", "unfreeze", "resume", "blockers", "incidents", "police"):
        sub.add_parser(n)
    p = sub.add_parser("add-task"); p.add_argument("id"); p.add_argument("title"); p.add_argument("description"); p.add_argument("acceptance", nargs="?", default=""); p.add_argument("--priority", type=int, default=5)
    for n in ("review", "approve", "reject", "apply"):
        sub.add_parser(n).add_argument("request_id")
    sub.add_parser("halt").add_argument("reason", nargs="?", default="manual halt")
    sub.add_parser("restore").add_argument("checkpoint_id")
    p = sub.add_parser("unblock"); p.add_argument("task_id"); p.add_argument("guidance")
    p = sub.add_parser("finding"); p.add_argument("incident_id"); p.add_argument("judgment"); p.add_argument("note")
    sub.add_parser("twe").add_argument("twe_id")
    sub.add_parser("profile").add_argument("principal", nargs="?", default="proposer")
    m = sub.add_parser("models"); m.add_argument("action", choices=["probe", "test", "snippet", "load", "download", "status"]); m.add_argument("arg1", nargs="?"); m.add_argument("arg2", nargs="?"); m.add_argument("arg3", nargs="?"); m.add_argument("--base-url", default=None)
    sv = sub.add_parser("serve"); sv.add_argument("--interval", type=float, default=30.0); sv.add_argument("--max-cycles", type=int, default=0)
    sub.add_parser("doctor")
    sub.add_parser("qualify").add_argument("principal", nargs="?", default="proposer")
    sub.add_parser("quickstart").add_argument("--force", action="store_true")
    u = sub.add_parser("ui"); u.add_argument("--port", type=int, default=8765); u.add_argument("--no-browser", action="store_true")
    a = ap.parse_args(argv)
    root = Path(a.root)
    try:
        if a.cmd == "init":
            lay = Layout.at(root)
            for f in (lay.constitution, lay.permissions):
                if not f.exists():
                    print(f"missing {f.name}; copy the template first", file=sys.stderr); return 2
            lay.state.mkdir(exist_ok=True); lay.workspace.mkdir(exist_ok=True)
            print(json.dumps(_kernel(root).status(), indent=2)); return 0
        if a.cmd == "halt":
            from .halt import HaltController
            state = Layout.at(root).state; state.mkdir(parents=True, exist_ok=True)
            HaltController(state, install_signal_handlers=False).write_stop_file(a.reason); print(f"STOP written: {a.reason}"); return 0
        if a.cmd == "freeze":
            (Layout.at(root).state / "FREEZE").write_text("frozen by human\n", encoding="utf-8"); print("FREEZE written"); return 0
        if a.cmd == "unfreeze":
            f = Layout.at(root).state / "FREEZE"
            if f.exists(): f.unlink()
            print("FREEZE removed"); return 0
        k = _kernel(root)
        if a.cmd == "status":
            print(json.dumps(k.status(), indent=2)); return 0
        if a.cmd == "verify-audit":
            ok, msg = k.audit.verify(); pok, pmsg = k.police.verify()
            print(("AUDIT OK: " if ok else "AUDIT BROKEN: ") + msg); print(("POLICE OK: " if pok else "POLICE BROKEN: ") + pmsg)
            for t in k.twe.ids():
                tok, tmsg = k.twe.verify(t); print(f"{t}: {'OK' if tok else 'BROKEN'} {tmsg}")
            return 0 if ok and pok else 1
        if a.cmd == "add-task":
            t = k.tasks.add(a.id, a.title, a.description, a.acceptance, a.priority)
            k.audit.append("human", "task_added", t.id, "ok", title=t.title); print(f"queued {t.id}"); return 0
        if a.cmd == "propose":
            res = k.propose()
            if res is None: print("nothing to do (see state/reports)"); return 0
            return _print_result(res, "ok")
        if a.cmd == "review":
            print(k.packet_text(a.request_id)); return 0
        if a.cmd in ("approve", "reject"):
            phrase = (k.c.approval_phrase if a.cmd == "approve" else k.c.rejection_phrase).format(request_id=a.request_id)
            print(f"To {a.cmd} {a.request_id}, type exactly:\n  {phrase}")
            return _print_result(k.approve(a.request_id, input("> ")), "recorded")
        if a.cmd == "apply":
            res = k.apply(a.request_id)
            rc = _print_result(res, "applied")
            return rc if rc else (0 if (res.output or {}).get("applied") else 1)
        if a.cmd == "resume":
            print(f"To resume, type exactly:\n  {k.c.resume_phrase}")
            if k.halt.resume(input("> "), k.c.resume_phrase):
                k.audit.append("human", "resume", "STOP", "ok"); print("resumed"); return 0
            print("phrase mismatch; still halted"); return 1
        if a.cmd == "checkpoints":
            for c in k.checkpoints.list(): print(f"{c.id}  files={c.file_count}  label={c.label}")
            return 0
        if a.cmd == "restore":
            k.halt.check(mutation=True); k.checkpoints.restore(a.checkpoint_id); k.audit.append("human", "restore", a.checkpoint_id, "ok"); print("restored"); return 0
        if a.cmd == "blockers":
            for b in sorted(k.blockers_dir.glob("*.md")):
                if ".resolved." not in b.name: print(b.stem); print("   " + b.read_text(encoding="utf-8").splitlines()[0])
            return 0
        if a.cmd == "unblock":
            t = k.unblock(a.task_id, a.guidance); print(f"{t.id} returned to queue with guidance"); return 0
        if a.cmd == "incidents":
            for i in sorted(k.incidents_dir.glob("*.md")):
                print(f"{i.stem}  [{'finding pending' if '- Judgment: (unrecorded' in i.read_text(encoding='utf-8') else 'finding recorded'}]")
            return 0
        if a.cmd == "finding":
            k.record_finding(a.incident_id, a.judgment, a.note); print("finding recorded"); return 0
        if a.cmd == "twe":
            return _print_result(k.dispatch(k.ctx_human, "read_twe", {"twe_id": a.twe_id}), "")
        if a.cmd == "police":
            return _print_result(k.dispatch(k.ctx_human, "read_police", {}), "")
        if a.cmd == "profile":
            ctx = k.runtime.context_for(a.principal)
            return _print_result(k.dispatch(ctx, "get_authorization_profile", {}), "")
        if a.cmd == "models":
            from . import localmodels
            if a.action == "probe":
                for row in localmodels.probe():
                    state = f"reachable, {len(row['models'])} models: {', '.join(row['models'][:8])}" if row["reachable"] else f"not reachable ({row.get('error', '')})"
                    print(f"{row['provider']:45} {row['base_url']:28} {state}")
                return 0
            if a.action == "test":
                principal = a.arg1 or "proposer"
                cfg = k.c.section("models").get(principal)
                if cfg is None:
                    print(f"no [models.{principal}] section", file=sys.stderr); return 2
                res = localmodels.smoke_test(cfg, allow_remote=bool(k.c.section("models").get("allow_remote_endpoints", False)))
                print(json.dumps(res, indent=2)); return 0 if res["reachable"] and res["json_object"] else 1
            if a.action in ("load", "download", "status"):
                cfg = dict(k.c.section("models").get("proposer", {}))
                allow = bool(k.c.section("models").get("allow_remote_endpoints", False))
                if a.action == "load":
                    print(json.dumps(localmodels.load_model(cfg, a.arg1, allow_remote=allow), indent=2, default=str)); return 0
                if a.action == "download":
                    if not a.arg1: print("usage: models download <model id>", file=sys.stderr); return 2
                    print(json.dumps(localmodels.download_model(cfg, a.arg1, allow_remote=allow), indent=2, default=str)); return 0
                if not a.arg1: print("usage: models status <job id>", file=sys.stderr); return 2
                print(json.dumps(localmodels.download_status(cfg, a.arg1, allow_remote=allow), indent=2, default=str)); return 0
            if a.action == "snippet":
                if not (a.arg1 and a.arg2 and a.arg3):
                    print("usage: models snippet PRINCIPAL PROVIDER MODEL [--base-url URL]", file=sys.stderr); return 2
                print(localmodels.snippet(a.arg1, a.arg2, a.arg3, a.base_url)); return 0
        if a.cmd == "serve":
            import time as _t
            cycles = 0
            print(f"serving: interval={a.interval}s max_cycles={a.max_cycles or 'unlimited'}; halt with `python -m kernel halt`")
            while not k.halt.stopped and (a.max_cycles == 0 or cycles < a.max_cycles):
                res = k.propose()
                cycles += 1
                stamp = _t.strftime("%H:%M:%S")
                if res is None:
                    print(f"[{stamp}] cycle {cycles}: idle or parked (see state/reports)")
                else:
                    print(f"[{stamp}] cycle {cycles}: {'ALLOW' if res.allowed else 'DENY ' + res.authz.reason} {json.dumps(res.output, default=str)[:160] if res.output else ''}")
                if k.pending_requests():
                    print(f"[{stamp}] {len(k.pending_requests())} request(s) awaiting your decision: {', '.join(k.pending_requests())}")
                _t.sleep(a.interval)
            print("serve stopped:", k.halt.reason() or "cycle limit reached"); return 0
        if a.cmd == "qualify":
            from . import qualify
            from .model import build_model
            cfg = k.c.section("models").get(a.principal)
            if cfg is None:
                print(f"no [models.{a.principal}] section", file=sys.stderr); return 2
            model = build_model(cfg, allow_remote=bool(k.c.section("models").get("allow_remote_endpoints", False)))
            print(f"qualifying {a.principal} ({getattr(model, 'name', '?')}) on {len(qualify.SCENARIOS)} scenarios; each is one model call ...")
            rep = qualify.run(root.resolve(), model, a.principal)
            for r in rep["results"]:
                print(f"  {'PASS' if r['passed'] else 'FAIL'}  {r['scenario']:24} {r['note']}  ({r['latency_s']}s)")
            print(f"{rep['passed']}/{rep['total']} passed; report: {rep['report_path']}")
            k.audit.append("human", "qualification_run", a.principal, f"{rep['passed']}/{rep['total']}", model=rep["model"], report=rep["report_path"])
            return 0 if rep["passed"] == rep["total"] else 1
        if a.cmd == "quickstart":
            from . import quickstart
            res = quickstart.seed(k.layout.workspace, k.tasks, force=a.force)
            for rel in res["created"]: print(f"created  workspace/{rel}")
            for tid in res["queued"]: print(f"queued   {tid}")
            for x in res["skipped"]: print(f"kept     {x}")
            k.audit.append("human", "quickstart", "workspace", "ok", created=res["created"], queued=res["queued"])
            print("next: python -m kernel models test proposer ; python -m kernel qualify ; python -m kernel propose"); return 0
        if a.cmd == "ui":
            from .ui import ControlPanel
            ControlPanel(k, port=a.port).serve(open_browser=not a.no_browser); return 0
        if a.cmd == "doctor":
            from . import localmodels
            import platform, subprocess
            print(f"python {platform.python_version()} on {platform.system()}")
            st = k.status()
            print(f"constitution v{st['constitution_version']} {st['constitution_sha256']}; permissions v{st['permissions_version']} {st['permissions_sha256']}")
            print(f"audit: {st['audit']}; police: {st['police']}; halted={st['halted']} frozen={st['frozen']}")
            for row in localmodels.probe():
                print(f"model server {row['provider'][:20]:20} {row['base_url']:28} {'reachable' if row['reachable'] else 'not reachable'}")
            for principal in ("proposer", "monitor", "police"):
                cfg = k.c.section("models").get(principal, {})
                print(f"[models.{principal}] provider={cfg.get('provider')} model={cfg.get('model')} base_url={cfg.get('base_url', '-')}")
            wrapper = k.c.section("execution").get("sandbox_wrapper")
            print(f"sandbox wrapper: {'configured' if wrapper else 'NOT configured (network isolation not provided)'}")
            print("isolation check: run `python tools/check_os_isolation.py --sandbox-uid <uid>` as the kernel user")
            rc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(Path(__file__).resolve().parents[1] / "tests")], capture_output=True, text=True)
            print("test suite:", rc.stdout.strip().splitlines()[-1] if rc.stdout.strip() else rc.stderr[-300:])
            return 0 if rc.returncode == 0 else 1
    except Halted as exc:
        print(f"HALTED: {exc}", file=sys.stderr); return 3
    except KernelError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr); return 4
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
