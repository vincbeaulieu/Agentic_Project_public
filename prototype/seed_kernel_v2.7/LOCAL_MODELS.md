# Running agents on local models (LM Studio, Ollama, llama.cpp, vLLM, Hugging Face)

The kernel talks to models through a small adapter interface (`kernel/model.py`); the authorization engine, TWE, audit and police do not depend on which model is used. Three principals can have a model: `proposer` (writes proposals), `monitor` (second opinion on proposals; a different family from the proposer, D3 SR-04) and `police` (behavioural review; flags only). Each is configured in `constitution.toml` under `[models.<principal>]`.

## Privacy default

`[models] allow_remote_endpoints = false` refuses any endpoint whose host is not `localhost`, `127.0.0.1`, `::1` or `host.docker.internal`. Project data therefore stays on this machine unless you set it to `true` (a data-classification decision, D3 §14). `huggingface_local` runs in-process and is always local; `huggingface_router` is remote.

## LM Studio

1. Start LM Studio, load a model (for a coding proposer: an instruct/coder model in the 7B–14B range, e.g. `qwen2.5-coder-7b-instruct`), enable the local server (default `http://localhost:1234/v1`).
2. `python -m kernel models probe` → the server and its model ids appear.
3. `python -m kernel models snippet proposer lmstudio <model id>` → paste the block into `constitution.toml`.
4. `python -m kernel models test proposer` → `reachable: true`, `json_object: true`, `call_field_present: true` expected. LM Studio supports `response_format` JSON mode; keep `json_mode = true`.

### LM Studio native REST API

Recent LM Studio versions also expose `/api/v1/models`, `/api/v1/chat`, `/api/v1/models/load`, `/api/v1/models/download` and `/api/v1/models/download/status/<job>`. `provider = "lmstudio_native"` uses them (`base_url = "http://127.0.0.1:1234"`, no `/v1`); `python -m kernel models load <id>` loads a model into memory, `models download <id>` starts a download and `models status <job>` polls it. The OpenAI-compatible `lmstudio` provider remains the verified default.

## Ollama

1. `ollama pull qwen2.5-coder:7b` (proposer) and, for the monitor, a different family, e.g. `ollama pull llama3.1:8b`.
2. Native API: `provider = "ollama"`, `base_url = "http://localhost:11434"`, `json_mode = true` (Ollama's `format: "json"`). Or the OpenAI-compatible endpoint: `provider = "openai_compatible"`, `base_url = "http://localhost:11434/v1"`.
3. `python -m kernel models test monitor`.

## llama.cpp server / vLLM / TGI

`provider = "openai_compatible"` with the server's `/v1` base URL (llama.cpp default `http://localhost:8080/v1`, vLLM `http://localhost:8000/v1`). `json_mode` depends on the server; if the smoke test reports `json_object: false`, set `json_mode = false` and rely on the prompt's format instruction.

## Hugging Face Transformers (in-process)

`pip install transformers torch accelerate` (a GPU is required for models above ~3B parameters in practice). Configure `provider = "huggingface_local"`, `model = "Qwen/Qwen2.5-Coder-7B-Instruct"` (a hub id or a local path), `device = "auto"`. The first call downloads the weights to the HF cache; subsequent calls use no network. A gated hub model needs `huggingface-cli login` once.

## Hugging Face inference router (remote)

`provider = "huggingface_router"`, `model = "<org>/<model>"`, `HF_TOKEN` in the environment, and `allow_remote_endpoints = true`. Remote: only for data classes the human has assigned to hosted models.

## What the smoke test does and does not show

`models test` sends one fixed prompt and reports latency, whether the reply is a JSON object, and whether it has the `call` field the kernel expects. It is a connectivity and format check. Qualification (D3 §8.2: known-answer questions, adversarial prompts, escalation and evidence-labelling scenarios) is a separate step before an agent receives authority.

## Model size guidance for the function-call format

The proposer must return one JSON object with a `call`, `args`, an evidence block and complete file contents. Models below ~7B parameters frequently fail the format; `json_mode = true` reduces but does not eliminate failures. A malformed response is not applied: the kernel requeues the task and records `model_output_rejected`; after `max_proposals_per_task` attempts the task is parked. If the smoke test passes but `propose` cycles produce repeated malformed outputs, use a larger or more instruction-tuned model, or lower `temperature`.
