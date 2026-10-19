---
name: "cowork-with-lmstudio"
description: "When to delegate part of a task to the user's local LM Studio models through a micro-task queue that does not pass through the conversation, and how to measure and verify their results."
---

# Coworking with LM Studio

This skill says **when and how** to bring the user's local models into a task. For one-off technical access (built-in browser, `127.0.0.1:1234`, `fetch` calls), follow the `lmstudio-local` skill.

## Principle

Local models are **fast, free but limited assistants**: 3 to 12 billion parameters, running on the GPU of an 8 GB laptop. Claude remains responsible for the final result:
- it prepares the instructions and splits the work into micro-tasks;
- it delegates through a **queue**, without waiting;
- it **verifies with deterministic rules and on the test bench** before using any result.

Any judgment that a local model repeats must eventually be taken over by a **deterministic classifier that Claude develops itself** (LC-015). This includes:
- the code;
- the training directory `00_competences_claude/entrainement/`;
- the checkpoints for moving from CPU to GPU;
- the test bench before adoption.

The local model's outputs go in there as "silver" labels.

## The normal path: the queue (zero tokens of load)

The load of a micro-task **never** goes through Claude's replies. Copying a batch into a JavaScript call costs as many tokens as reading it again (LC-016).

- **Deposit.** `00_competences_claude/outils/file_lmstudio_vN.py deposer …` (or `deposer-embeddings`), preferably run on the PC, in the local VM. The batch is written to `Revision\00_espace_cloud_claude\file_lmstudio\entree\`.
- **Processing.** The Windows worker `worker_lmstudio` (started by the user; see the folder's README, which also describes the launcher) processes the queue:
  - priorities from 0 (urgent) to 3 (background), with aging: no starvation;
  - grouping by model: few reloads;
  - re-queuing if LM Studio is unreachable.
- **Tracking.** `journal\etat.json`: pending, processed, errors, current model.
- **Collection.** `file_lmstudio_vN.py recolter …` copies the results, versioned, into the work folder.
- **Meanwhile, Claude works on something else.** It never waits for LM Studio.

The browser path (`javascript_tool` in the `127.0.0.1:1234` tab) is reserved for:
- tests with a few calls;
- test benches, when the worker is not running.

In that case, keep the load in `window.__T` (and `localStorage`) so it can be reused with other models or instructions without sending it again.

## Mandatory settings for a call

- `reasoning_effort: "none"`. Without it, gemma-4 and qwen3.5 reason before answering: about 160 tokens and 1.9 s per call, versus 0 tokens and 0.4 s.
- `temperature` 0 (at most 0.3 for a rewording).
- Bounded `max_tokens`: 40 for a closed choice.
- `response_format` of type `json_schema`, with an `enum` of the allowed values. The grammar then guarantees the format.
- A short, named and versioned instruction (`consignes\MT-…_vN.txt`), cited by the task rather than repeated. One example if needed.
- Context: keep 4,096 to 8,192 tokens per call.

## How to integrate it into a task

1. **Tools first.** Anything a hard rule settles does not go to the model. Examples: rule on the author's notes, placeholder markers, numbers or references that have disappeared.
2. **Adopted classifier first, if one exists.** It decides the safe cases, above its confidence threshold. Only the uncertain cases go to the queue.
3. **Split into micro-tasks** (`microtaches_vN.py generer`): unit, independent sub-tasks, a closed question, an input of fewer than 1,500 characters, allowed values.
4. **Measured pilot.** A reference sample stratified by genre, 2 passes, several models. Per model: accuracy, macro F1, ms, consistency between passes (`microtaches_vN.py evaluer`). The references enter the training directory as gold.
5. **Rules after the model** (`microtaches_vN.py combiner`), also measured on the test bench.
6. **Scale up through the queue**, using the best rules + model pair for each type of micro-task.
7. **Verify** (see below), correct or redo what fails, then integrate. Collect the outputs (silver) and the reviewed sample (gold) in the training directory.
8. **Report** to the user, in one line, what the local model did and the level of verification.

## Choosing the model

Re-read `/api/v0/models` first. Benchmarks measured on 15 Oct 2026, reasoning off:

| Model | Use | Median time |
|---|---|---|
| `google/gemma-4-e2b` | bulk sorting, unreliable (0.68 on requests) | 0.24 s |
| `google/gemma-4-e4b` | request classification; with rules: 0.895 | 0.45 s |
| `google/gemma-4-12b-qat` | more careful classification and rewording: 0.895 | 2.9 s |
| `qwen/qwen3.5-9b` | general purpose, good French; text comparison (presence of a piece of information), with rules: 8/8 | 2 to 11 s |
| `qwen/qwen3-coder-next` | simple code, conversions, regex, short scripts | — |
| `deepseek/deepseek-r1-0528-qwen3-8b` | short step-by-step reasoning (slow, verbose) | — |
| `text-embedding-nomic-embed-text-v1.5` | embeddings: search, deduplication, grouping, classifier features | — |
| `orpheus-3b-0.1-ft` | speech synthesis only, no text | — |

All outputs were consistent between two passes at temperature 0.

## Speed and capacity (benchmarks)

- First call on a model: loading included, 8 to 30 s.
- Only one model fits comfortably at a time in 8 GB of VRAM. The worker's grouping by model avoids switching back and forth.
- As long as LM Studio occupies the GPU, the classifiers train on the CPU.
- The small models (e2b, e4b) are the fastest but the least reliable.
- Measure the time of the first calls and adjust the batch size.

## Tasks to give it

- Classification, labelling, sorting, category detection on many items.
- Comparison of two short texts (information present, partial, absent).
- Extraction of fields into a fixed format (names, dates, amounts from short texts).
- Short summaries of isolated passages; a first pass of synthesis that Claude refines.
- Rewording, spelling correction, change of tone, draft translation.
- Simple, repetitive code: format conversions, small functions, regex, comments.
- Embeddings, to search, group or deduplicate, and as features for the classifiers that Claude develops.
- "Silver" labels for the training directory of those classifiers.
- Data that the user prefers to keep on their machine.
- Generation of variants or ideas in volume, which Claude then filters.

## Tasks NOT to give it

- Long or multi-step reasoning; legal, financial or medical analysis.
- Recent or precise facts (local models hallucinate and have no web access).
- Calculations: do them in code, never with the model.
- Final deliverables sent as they are to a third party.
- Long documents in one piece (limited context, loss of coherence).
- Irreversible decisions.

## When to suggest it

Suggest the local model, in one sentence, when at least one of these cases applies:
- **Volume**: dozens or hundreds of similar items to process.
- **Confidentiality**: the user wants the data to stay on their PC.
- **Cost / quota**: a simple, repetitive task that would use many tokens (only through the queue: otherwise the transport costs as much).
- **Preparation**: a rough first pass before Claude's fine work.
- **Test bench**: measuring instruction or model variants on the same load.

Do not suggest it for a single short task: Claude is faster alone.

## Verification (mandatory)

Verify quickly; do not redo everything:
1. **Format**: guaranteed by `json_schema`; a value outside the list is rejected and the task is run again.
2. **Deterministic rules** applied after the model, and disagreements reported.
3. **Sample**: review 10 to 20% of the outputs, at least 3, atypical cases first.
4. **Consistency**: values in the expected categories, no empty fields, plausible lengths.
5. **Fidelity**: for an extraction or a summary, check every number, name or date against the source on the sample.
6. **Threshold**: beyond about 10% errors in the sample, change the model, tighten the instruction, add a rule, or do the task yourself.
7. **Classifier under development**: adopted only if it equals or exceeds the rules + model pair on the same gold examples, in cross-validation. First trials of 15 Oct 2026, not adopted:
   - naive Bayes: 0.50;
   - softmax regression on n-grams: 0.70, versus 0.90 for the baseline, on 20 gold examples.
8. **State** in the final answer what came from the local model and the level of verification done.
