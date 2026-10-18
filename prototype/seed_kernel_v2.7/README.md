# seed_kernel_v2.7 — default-deny, function-call kernel with live model progress

**Start by double-clicking `Start AOP Kernel.bat`** (Windows). It checks for Python 3 (installs it with winget if missing), installs the one dependency, runs the self-tests on first start, and opens the control panel at http://127.0.0.1:8765/ in your browser. Command-line use is unchanged (`python -m kernel ...`).

Version 2.7 makes model calls observable and interruptible. The OpenAI-compatible adapter streams (`stream = true`), separates the reasoning deltas that LM Studio / llama.cpp emit for reasoning models (`reasoning_content`) from the answer, and exposes a `Progress` object; `timeout_seconds` becomes an idle timeout between chunks and `max_wall_seconds` bounds the whole call; `extra_body` passes server options through (e.g. `reasoning_effort`). The control panel runs model calls (assistant draft, proposer cycle, qualification, smoke test) as background jobs: a card shows elapsed time, the reasoning as it streams, the answer so far and a Cancel button (closing the connection stops LM Studio's generation); other actions are refused while a job runs. Every call's reasoning and answer are written to `state/model_traces/`; a reasoning-only reply (budget exhausted while thinking) is reported as such in the chat and in the audit log instead of a bare parse failure. 91 tests.

Version 2.6 adds `[paths] workspace_dir` (constitution v0.7.0): the governed workspace may live outside the kernel folder. The shipped value `../../platform/aop_platform_v0.1` points at the platform (D7), so the agent's proposals change the platform's `src/**`, `tests/**` and `docs/**` and the kernel runs the platform's own test suite before keeping a change. The kernel refuses a value that overlaps its own folder, `state/` or `kernel/`, or that contains the kernel folder. `quickstart` keeps the files of an existing workspace and queues four platform backlog tasks (ADR 0007, two query methods with tests, a task template). 91 tests.

Version 2.5 adds the assistant sidebar (`kernel/assistant.py`), shown on every page of the control panel: the human describes a request in plain words, the assistant model returns a draft of the task fields (title, description, acceptance criteria, priority) and any clarifying questions, and the draft pre-fills the New-task form. The assistant has no authority and no function interface: it queues, approves, runs and reads nothing; every call is audited (`task_drafted`, input and output hashes) and logged to `state/assistant/chat.jsonl`; its calls are counted separately from the proposer's. Configured by `[models.assistant]` (constitution v0.6.0): `provider = "proposer"` reuses the proposer model, `"dummy"` disables the sidebar. Refused while halted. 91 tests.

Version 2.4 adds the Tasks page to the control panel: a *New task* form (id, title, description, acceptance criteria, priority) that is the human's channel for requesting work from the agent, the task queue by state, and a *Return to queue* form for parked tasks. A task without acceptance criteria is refused (Definition of Ready). Each queued task is written to the audit log (`task_added`, `via = control_panel`).

Version 2.3 adds the control panel (`python -m kernel ui`): dashboard (tasks, pending requests, controls, integrity, today's report), request pages with the packet and approve/reject/apply forms, blockers with guidance forms, incidents with finding forms, models (probe, smoke test, qualify), audit and police tails, help. It binds to 127.0.0.1 only, every POST carries a per-process token, and every action is dispatched as the `human` principal through the same authorization engine as the CLI.

Version 2.2 adds: robust parsing of local/reasoning model output (`<think>` blocks, code fences, trailing text, JSON-mode fallback when a server rejects `response_format`); `python -m kernel qualify [principal]` (seven behavioural scenarios run in throw-away kernel roots, report under `state/qualification/`); `python -m kernel quickstart` (workspace skeleton `src/aop`, smoke test, docs, and tasks T-001…T-004 so the project starts building itself); `RUN_ON_WINDOWS.md`. 74 tests.

Version 2.1 adds local model support to v2.0: providers `lmstudio`, `ollama` (native API), `openai_compatible` (llama.cpp, vLLM, Ollama `/v1`, HF TGI, gateways), `huggingface_local` (in-process Transformers) and `huggingface_router` (remote); a privacy gate that refuses non-local endpoints unless `[models] allow_remote_endpoints = true`; a `[models.police]` section; `python -m kernel models probe|test|snippet`; `serve` for continuous operation; `doctor` for environment checks. See `LOCAL_MODELS.md`. 63 tests (34 security, 20 operational, 9 local-model). Constitution v0.5.0.

Version 2.0 implements rule R04 (`04_rules_and_code_of_practice/R04_capability_security_model_v1.md`): a default-deny capability model with authenticated execution contexts, a function-call API as the agent's only interface, kernel-managed append-only TWE storage, approvals bound to request hashes, fail-closed authorization, an R04 §19 audit schema, and a police subsystem (deterministic engine plus an optional police LLM that cannot authorize anything). It keeps everything from v1.3 (constitution, halts, checkpoints, rollback, escalation and blockers, incidents and findings, refresher, evidence block, agent record). Constitution v0.4.0; permissions v0.1.0. 54 tests: 34 in `tests/test_security.py` mapped to R04 §39 AC-01…AC-30 and invariants I1–I18, 20 operational safety tests in `tests/test_kernel.py`.

Size: approximately 2,300 lines of standard-library Python (kernel) plus tests; one dependency (`pytest`; `tomli` on Python 3.10).

## Architecture

```
model output ─► parsed function call ─► Kernel.dispatch(ctx, function, args)
                                            │
                    ┌───────────────────────▼────────────────────────┐
                    │ AuthorizationEngine (deterministic, no model)   │
                    │ identity → function → resources → capability →  │
                    │ scope → halt → request state → evidence →       │
                    │ approval → policy;  any exception → DENY        │
                    └───────┬───────────────────────────┬────────────┘
                          DENY                        ALLOW
                            │                           │
                    audit event (R04 §19)         handler executes
                            │                           │
                    PoliceEngine.inspect          audit event (output hash)
                            │
                    police.jsonl (hash chain); escalation entry in twe/human when severity requires
```

Principals and capabilities are declared in `permissions.toml` (human-only file; SHA-256 audited at start). Functions are declared in `kernel/loop.py::_register_functions`, each with its required permission, resource extractor and evidence/approval requirements. A function that is not registered is unknown → DENY. A registered function whose permission no principal holds → DENY for everyone. Identity comes only from `KernelRuntime.context_for(...)`; `agent_id` in arguments is ignored (and denied when it differs).

```
seed_kernel_v2.7/
  Start AOP Kernel.bat  double-click launcher (Windows)
  constitution.toml    rules of operation (paths, budgets, phrases, escalation, evidence, reflection, incidents)
  permissions.toml     principals and explicit capabilities (proposer, human, police, monitor)
  kernel/
    authz.py           Permission, Capability, PermissionStore, AgentContext + KernelRuntime, FunctionRegistry, AuthorizationEngine
    twe.py             TWEService: append-only hash-chained TWE logs; immutable requests; read returns copies only
    police.py          PoliceEngine (deterministic rules, hash-chained police.jsonl, escalation) + llm_review (flags only)
    audit.py           AuditLedger with R04 §19 fields; hash chain; redaction
    loop.py            Kernel: function registry, dispatch, handlers, proposer cycle, packets, blockers, incidents, reports
    constitution.py    load/validate/freeze; model-facing summary (categories, high-stakes classes, precedence, evidence)
    policy.py          deterministic content rules for patches (BLOCK / ESCALATE / REVIEW)
    ui.py              control panel (127.0.0.1 only): dashboard, tasks, requests, blockers, incidents, models, audit, help; assistant sidebar
    assistant.py       task-drafting assistant (no authority): free text -> draft of task fields for the New-task form
    model.py, localmodels.py, qualify.py, quickstart.py, checkpoint.py, halt.py, sandbox.py, tasks.py, cli.py
  tools/
    check_os_isolation.py   verifies ownership/mode bits of protected storage against the sandbox uid (AC-09, AC-26, AC-27)
    setup_os_isolation.sh   two-user layout (kernel user owns state/, permissions, constitution, kernel; sandbox user runs tests)
  tests/               test_security.py (R04 §39), test_kernel.py, test_local_models.py, test_qualify_quickstart.py, test_ui.py
  state/               kernel-managed: audit.jsonl, police.jsonl, twe/, approvals/, checkpoints/, tasks/, blockers/, incidents/, training/, assistant/, model_traces/
  workspace/           default governed workspace; replaced by [paths] workspace_dir (the platform) in the shipped constitution
```

## Functions available to the proposer (default permissions)

`get_authorization_profile`, `read_workspace_tree`, `read_workspace_file`, `read_twe` (own TWE), `propose_patch` (scopes `workspace/src/**`, `docs/**`, `tests/**`, `README.md`; requires the evidence block), `report_blocker`, `abstain`, `request_action` (recorded; no executor at this stage). Not available: `record_approval`, `apply_approved_request`, `run_tests`, `read_audit`, `read_police`, `police_llm_review`, and every unregistered function.

## Quick start

```bash
cd seed_kernel_v2.7
python -m pytest -q                       # expected: 91 passed
python -m kernel init
python -m kernel models probe             # which local servers are running (LM Studio :1234, Ollama :11434, llama.cpp/vLLM :8000/:8080)
python -m kernel models snippet proposer ollama qwen2.5-coder:7b   # paste into constitution.toml [models.proposer]
python -m kernel models test proposer     # connectivity + JSON-format smoke test of the configured model
python -m kernel doctor                   # environment, models, isolation reminder, test suite
python -m kernel qualify proposer         # behavioural scenarios against the configured model (nothing in state/ is touched except the report)
python -m kernel quickstart               # seed workspace skeleton + tasks T-001..T-004
python -m kernel profile proposer         # the proposer's authorization profile
python -m kernel add-task t1 "add mul" "add a mul(a,b) function to src/calc.py" "tests pass"
python -m kernel propose                  # one model call -> one function call -> dispatch (dummy model abstains)
python -m kernel review req-...           # approval packet (request hash shown)
python -m kernel approve req-...          # human types the phrase; dispatched as record_approval
python -m kernel apply req-...            # dispatched as apply_approved_request: checkpoint -> write -> tests -> checkpoint | rollback
python -m kernel verify-audit             # audit chain, police chain, every TWE chain
python -m kernel police                   # police events
python -m kernel twe twe/human            # escalations from the police engine land here
```

Continuous operation: `python -m kernel serve --interval 30` runs proposer cycles until `halt`, `freeze` (mutations) or `--max-cycles`; each cycle is one model call and one function call, and pending approval requests are listed after each cycle.

Halting, freezing, resuming, blockers, incidents and findings are unchanged from v1.2/v1.3 (`halt`, `freeze`, `unfreeze`, `resume`, `blockers`, `unblock`, `incidents`, `finding`).

## Deployment checks before use with a model endpoint

1. Two OS users: `sudo tools/setup_os_isolation.sh .` then `python tools/check_os_isolation.py --root . --sandbox-uid <sandbox uid>` must print `RESULT: PASS`.
2. `sandbox_wrapper` configured under `[execution]` (for example `docker run --rm --network none --user <sandbox uid> ...`).
3. A different model family for `[models.monitor]`, and a police model for `police_llm_review` if behavioural review is wanted (its output is flags only).
4. `permissions.toml` reviewed line by line: every capability is a positive grant; nothing is granted by role name or prompt.
