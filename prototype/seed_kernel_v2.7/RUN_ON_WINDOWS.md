# Running the kernel on Windows with LM Studio

## Simplest: double-click

1. Start LM Studio, load `google/gemma-4-12b-qat`, start its server on port 1234 (the default).
2. In `Agentic_Project\prototype\seed_kernel_v2.7\`, double-click **`Start AOP Kernel.bat`**.
   First start: it finds Python (or installs it with winget), installs `pytest`, runs the self-tests (about 30 seconds), and opens http://127.0.0.1:8765/ in your browser. Keep the black window open; closing it stops the panel.
3. In the panel: **Models → Smoke-test proposer** (checks the model answers in the expected format), **Models → Qualify proposer** (seven behavioural scenarios), **Dashboard → Quickstart** (queues the first four platform tasks; the workspace is `Agentic_Project\platform\aop_platform_v0.1`), **Dashboard → Run one proposer cycle**, then open the request under *Awaiting your decision*, read the packet, type the approval phrase, click **Apply**.
4. To ask the agent for something of your own, either type your request in plain words in the **Assistant** box on the right of any page and click *Draft a task from this* — the New-task form on the Tasks page is filled in for you (answer the assistant's questions to refine it), then review the fields and click *Queue this task* — or fill in **Tasks → New task** by hand. Fill in a title, a description (which files, what behaviour, what not to touch) and acceptance criteria (how you will judge it done), click *Queue this task*, then **Dashboard → Run one proposer cycle**. There is no chat channel: the task file is the directive the agent receives. If the agent needs information it answers with a blocker (Blockers page: answer with guidance and the task returns to the queue); if it proposes a change, the request appears for your decision.

## While the model works

Every model call runs in the background. A blue card at the top of the panel shows the elapsed time, the model's reasoning as it streams (reasoning models such as `google/gemma-4-12b-qat` think before they answer), the answer so far and a **Cancel** button; the page refreshes every 3 s. The full reasoning and answer of each call are saved under `state\model_traces\`. If the card ends with reasoning but an empty answer, the model used its whole `max_tokens` budget thinking: make the request shorter, raise `max_tokens`, add `extra_body = { reasoning_effort = "low" }` to `[models.proposer]` in `constitution.toml` (honoured by servers that support it), or load a non-reasoning instruct model (e.g. `qwen2.5-coder-7b-instruct`) and run **Qualify** again. A generation speed of about 5 tokens/s means the model is partly running on the CPU; a smaller model or more GPU offload in LM Studio makes each cycle several times faster.

Everything below is the command-line equivalent.

The kernel must run on the machine where LM Studio's server is reachable as `localhost:1234` — your Windows host (native Python) or WSL. It cannot run inside the Cowork VM, whose network is restricted to an allowlist.

## 0. One-command first session

```powershell
cd C:\path\to\Agentic_Project\prototype\seed_kernel_v2.7
powershell -ExecutionPolicy Bypass -File tools\first_session.ps1
```

This runs the tests, `init`, `models probe`, `models test`, `qualify`, `quickstart` and one `propose` cycle, and writes everything to `state\first_session.log` plus the usual `state\` files (qualification report, reports, TWE, audit). Because `state\` is inside the shared Agentic_Project folder, the reviewer in the Claude session can read those results directly. "Serve on Local Network" in LM Studio is not required for this (the kernel runs on the same machine as LM Studio); enable it only if the kernel runs in WSL.

## 1. Python and tests (PowerShell)

```powershell
cd C:\path\to\Agentic_Project\prototype\seed_kernel_v2.7
python --version                      # 3.11 or later recommended (3.10 works with: pip install tomli)
pip install pytest
python -m pytest -q                   # expected: 91 passed
```

## 2. LM Studio server

In LM Studio: load a model (a coder/instruct model of 7B–14B parameters for the proposer, e.g. `qwen2.5-coder-7b-instruct` or `qwen2.5-coder-14b-instruct`), open the Developer/Server tab, start the server on port 1234. Then:

```powershell
python -m kernel init
python -m kernel models probe                                   # lmstudio ... reachable, N models: <ids>
python -m kernel models snippet proposer lmstudio <model id>    # prints the [models.proposer] block
```

Paste the block over the `[models.proposer]` section in `constitution.toml` (edit by hand; the kernel records the hash change at the next start). For the monitor, load a second model of a different family in LM Studio (LM Studio can serve several loaded models) and paste a `[models.monitor]` block the same way; set `model_monitor_enabled = true` under `[monitor]` when you want the second opinion active.

### If the OpenAI-compatible endpoint is not the one your LM Studio exposes

Your LM Studio lists a native REST API (`/api/v1/models`, `/api/v1/chat`, `/api/v1/models/load`, `/api/v1/models/download`, `/api/v1/models/download/status/:job_id`). The kernel has a provider for it: `provider = "lmstudio_native"`, `base_url = "http://127.0.0.1:1234"`. `models probe` shows both rows (`lmstudio` = `/v1/chat/completions`, `lmstudio_native` = `/api/v1/...`); use whichever reports `reachable` with your model listed, then `models test proposer`. The native provider locates the reply text in the common response shapes; if `models test` reports an unexpected response shape, paste the JSON it printed and the adapter can be adjusted. `python -m kernel models load google/gemma-4-12b-qat`, `models download <id>` and `models status <job>` call the native load/download endpoints.

## 3. Smoke test and qualification

```powershell
python -m kernel models test proposer     # reachable, latency, json_object: true, call_field_present: true
python -m kernel qualify proposer         # 7 behavioural scenarios; report in state\qualification\
```

`qualify` runs seven scenarios in throw-away kernel roots (nothing in your state is touched): a routine change, a request to modify `kernel/`, a task referring to a spec that does not exist, a misleading directive, an injected instruction, a wrong test that pressures the model to weaken it, and an out-of-scope probe. A pass is determined from the function the model called and the kernel's authorization result. A model that fails `injected_instruction`, `protected_path_request` or `test_weakening_pressure` should not be given tasks; try a larger or more instruction-tuned model, `temperature = 0.1`, and keep `json_mode = true`.

## 4. First self-build tasks

```powershell
python -m kernel quickstart               # seeds workspace\ (src/aop, tests, docs) and tasks T-001..T-004
python -m kernel propose                  # one model call -> one function call; T-001 is a documentation task (low risk)
python -m kernel review <request id>      # the packet: evidence, flags, full file contents, request hash
python -m kernel approve <request id>     # type the phrase exactly
python -m kernel apply <request id>       # checkpoint -> write -> tests -> checkpoint | rollback
python -m kernel serve --interval 60      # continuous cycles; approve/apply remain manual commands
```

Everything the kernel does is under `state\`: `reports\<date>.md`, `approvals\pending\`, `blockers\`, `incidents\`, `twe\`, `audit.jsonl`, `police.jsonl`. `python -m kernel verify-audit` checks all chains.

## 5. Isolation on Windows

`tools/setup_os_isolation.sh` and the two-user layout are POSIX. On Windows without WSL the OS-level check reports NOT_APPLICABLE; the test step then runs as your user with a restricted environment and a timeout only. Two options: run the kernel in WSL and apply the two-user layout there (LM Studio on the host is reachable from WSL as `localhost:1234` on recent Windows versions, otherwise via the host IP shown by `ipconfig` — add it to `[models]` with `allow_remote_endpoints = true` only if that address is on your own machine); or install Docker Desktop and set `sandbox_wrapper` under `[execution]` to run the test command in a `--network none` container. Until one of these is in place, treat the setup as Stage 1 with reduced isolation: review every packet before approving, keep proposals small, and do not point the workspace at anything containing personal data.
