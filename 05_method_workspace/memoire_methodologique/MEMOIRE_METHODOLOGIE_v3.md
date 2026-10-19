# Work methodology memo (v3, 15 Oct. 2026)

**Status: `PROPOSÉ` ("PROPOSED"), awaiting approval by the user.** The authoritative version is the one given by `python3 00_competences_claude/outils/memoire_v1.py courant`. I read it every working day, at the start of the session. A new version is always a new file, and I use it only once it is approved.

**v3:**
- micro-task queue and permanent worker (priority scheduler without starvation, grouping by model, never waiting);
- classifiers developed by Claude (ML development of its tools): training directory, CPU/GPU checkpoints, confidence routing, adoption on the test bench;
- corresponding definitions.

**v2:**
- addition of the definitions (§1);
- no person's name: only roles;
- "when possible" for the replacement of agents;
- token economy;
- micro-tasks for local models.

## 1. Definitions

| Term | Meaning in this memo |
|---|---|
| **User** (or administrator, end user) | The person I work for. They decide and approve. I never name them in my own documents. |
| **Colleagues** | The other people: reviewers, commenters, recipients. Never named in my own documents. Designated by their role ("reviewing colleague", "invited colleague") or by a stable letter ("Colleague A"). |
| **My own documents** | What I use to work: skills, competence workspace, memo, rules, lessons, briefs, work folders and plans, scripts. The **documents delivered to the user** (reports, modification logs, deliverables) keep the original names. |
| **Tool** | A versioned script of `00_competences_claude/outils/`. It is:<br>- **deterministic**: same inputs, same output byte for byte, without an LLM;<br>- provided with a standard header (`OUTIL` ("TOOL"), `VERSION`, `RESUME` ("SUMMARY"), `USAGE`, `ENTREES` ("INPUTS"), `SORTIES` ("OUTPUTS"), `CATEGORIE` ("CATEGORY"), `BANC` ("TEST BENCH"), `REMPLACE` ("REPLACES"));<br>- listed by the catalogue;<br>- measured on a test bench.<br>A script specific to a single job goes in `90_scripts/` of that job. |
| **Agent** | A language model to which I entrust a sub-task: a Claude sub-agent, or a local model through LM Studio. |
| **Local model** | A small model (3 to 12 billion parameters) that runs on the user's PC, through LM Studio (`127.0.0.1:1234`, called from the built-in browser). It is free, fast and limited. |
| **Micro-task** | A sub-task so small that a simple local model does it quickly. It has:<br>- a single closed question;<br>- a short input (fewer than 1,500 characters);<br>- an imposed JSON output, with permitted values;<br>- a temperature from 0 to 0.3.<br>Its result is verified by a tool. |
| **Deterministic** | A result that depends only on the inputs: hard rules, patterns, checksums, schemas, instant categorization. The check: two runs give the same output checksum. |
| **Evaluator** | A tool that scores an agent's work or a deliverable using hard rules, and returns `BILAN conforme` ("overall result: compliant") or the list of gaps. |
| **Test bench** | Fixed cases, with their expected result, that measure a tool or an agent and compare two versions. |
| **Performance** | Seven distinct measures:<br>- alignment: rules and instructions followed;<br>- quality: accuracy, F1;<br>- speed;<br>- resources used: CPU, memory, tokens;<br>- resources consulted: volume read;<br>- compactness: size of the code and of the outputs;<br>- share of deterministic automation. |
| **Delegation** | A sub-task entrusted to an agent, recorded with its brief, its output schema, its evaluator and its measured results. |
| **Lesson** | A rule drawn from an error or an instruction. It is dated, has its evidence, and is linked to an automatic check (or entered on the "to automate" list). |
| **Deliverable** | The file handed to the user. It carries a version `vM.0.0`, it is read-only in `98_livrables`, and its editable copy is in `99_livrables_modifiables`. |
| **Version** | The suffix `_vN`, `_vX.Y.Nc` or `a` (revision by Claude or by the author), or `_vM.0.0` (deliverable). Never overwrite: a change makes a new version. |
| **Micro-task queue** | Folder `Revision\00_espace_cloud_claude\file_lmstudio\`: batches dropped as files (`entree\`), processed by the Windows **worker** `worker_lmstudio` (started by the user), results as files (`sortie\`). No data passes through my replies. |
| **Scheduler** | Choice of the next task in the queue: priority with aging (a task that waits gains priority: no starvation), grouping by model (few reloads). |
| **Classifier** | A machine-learning tool that **I develop** like any script: code, features, training, test bench, versions. It is not supplied ready-made. It takes over, case by case, a repetitive judgement entrusted to local models or agents. |
| **Training directory** | `00_competences_claude/entrainement/`: task specifications, labelled examples in immutable batches with their provenance, embedding cache, models, test benches. It grows with each job. |
| **Label quality** | gold: the user's correction or a verified judgement by Claude; silver: local model + rules; bronze: rule alone. Evaluation covers gold only. |
| **Checkpoint** | Portable `.npz` file of the complete state of a training run (parameters, moments, step, epoch, random generator, data checksum): training resumes where it stopped, on CPU or GPU. |
| **Confidence routing** | An adopted classifier decides alone above a threshold computed for a target precision; below it, the micro-task goes into the queue and its answer comes back as an example. |
| **Backup** | The copy from the cloud to the PC (`sync-cloud-pc` skill), proved by `N / N conformes` ("N / N compliant"). |

## 2. Requirements

| # | Requirement | Check |
|---|---|---|
| E1 | **Deterministic first.** Every rule written is verified by a tool, not by an LLM. | Test bench: `déterministe` ("deterministic"), `sans LLM` ("without LLM") |
| E2 | **Tools rather than agents.** Every recurring task becomes a tool that eventually replaces, **when possible**, the agent that did it. Agents keep the judgement that tools cannot yet provide. | `taches/`: automated, to-do and non-automatable steps; automatic share measured |
| E3 | **Micro-tasks for local models.** Work entrusted to an agent is first split into micro-tasks for a local model. A Claude sub-agent is used only for what a local model cannot do, with the user's approval. | Local-model test bench (quality, speed) on a reference sample |
| E4 | **Evaluated delegation.** The output is typed, the evaluator deterministic; I rerun it myself and record the result. | `delegation_v1.py` |
| E5 | **Measured improvement.** New version, comparison on the test bench, adoption only if quality, alignment and determinism do not decrease. | `banc_v1.py --comparer` |
| E6 | **Token economy.** My tokens are limited each day. I do not reread what I already know; I consult the catalogue rather than the tools; I write short messages, without repetition; I have the tools and local models process the volume; I do not pass large volumes of data through my replies. | Tokens recorded per delegation |
| E7 | **Version everything, overwrite nothing**, this memo included. | Rules N and E5 |
| E8 | **Mandatory organization** of a work folder: `00_sources`, `01_…` to `89_…`, `90_scripts`, `95_journal`, `98_livrables`, `99_livrables_modifiables`, `LISEZMOI`, `TRAVAIL`. | Rules O1 to O6 |
| E9 | **Default evaluation of every deliverable**: verdict `CONFORME` ("COMPLIANT") required. | `livrer_v1.py` then `evaluer_travail_v1.py` |
| E10 | **Continuous, strict and mandatory local backup**: after each file produced, before and after each batch of agents, at most every 15 min; full mode at the end of each step; never overwrite on the PC. | `verifier_sauvegarde_v1.py` |
| E11 | **Structured work**: task list, audit, plan before execution, state in `LISEZMOI`. | — |
| E12 | **All available competences**: session skills (docx, xlsx, pdf, review, corrections, log, transcript, orchestration, sync, LM Studio…) and catalogue tools. | Skills used noted in the audit |
| E13 | **No person's name in my own documents**: only roles (§1). Delivered documents keep the names. | Name detector (checksums, no plain-text list) |
| E14 | **Lessons linked to a check.** | `lecons_v1.py verifier` |
| E15 | **User approval** for: a version of the memo, a lesson, a skill, an agent org chart, an irreversible action. | Approval register |
| E16 | **Stay reachable**: short calls, short waves, messages read between two waves. | — |
| E17 | **Lessons from the report**: LC-008 (read the request, not the gesture), LC-009 (check that the fix settles the point raised), LC-010 (reviewing colleagues flag, the user decides). | Detectors DR-01 to DR-07; check L3 |

| E18 | **Queue and scheduler.** Every series of micro-tasks goes through the queue, never through my replies; I do not wait for it: I drop, I work, I collect. | `file_lmstudio`, `journal\etat.json` |
| E19 | **Developed classifiers.** Each repetitive judgement has its learning task. The training directory is fed with each job (gold, silver, bronze). Training is done on CPU when the GPU is busy or absent, with checkpoints to move to the GPU. Adoption on the test bench, then confidence routing. | `donnees_entrainement`, `entrainer_classifieur`, resume and cross-validation test benches |

## 3. Daily protocol

1. Restore `00_competences_claude` from the PC if it is missing.
2. Read the approved version of this memo (`memoire_v1.py courant`).
3. Read the latest catalogue and the lesson register, without rereading the tools.
4. Run `lecons_v1.py verifier`, `delegation_v1.py verifier` and `verifier_sauvegarde_v1.py`.
5. Remind the user of pending approvals.

## 4. Task protocol

1. **Frame**: the user's constraints, applicable skills and tools, folder created by `creer_travail`.
2. **Process with tools** everything that can be: extraction, detectors, pre-classification.
3. **Split the rest into micro-tasks** for a local model: strict prompt, JSON output. Have them verified by a tool (format, permitted values, consistency with the detectors), then reread a sample of 10 to 20%.
4. **Adopted classifier first**, if there is one: it decides the safe cases; only the uncertain cases go to micro-tasks.
5. **Measure first**: a pilot on a small reference sample establishes the quality and speed of the local model before any scaling up.
6. **My judgement** covers the residue: disagreements, detector findings, control sample.
7. **Deliver** through `livrer_v1.py`, then back up.
8. **Learn**: my verified judgements and the outputs of the local models enter the training directory; lessons, new deterministic rules drawn from repeated verdicts, tools improved on the test bench, catalogue and summary regenerated.
9. **Full backup**, then `verifier_sauvegarde`.

## 5. Managing this memo

`memoire_v1.py` manages the versions:
- `etat`: lists the versions and their status;
- `courant`: gives the approved version, after verifying its checksum;
- `proposer`: records a new version as proposed;
- `approuver <N> --citation "…"`: only after the user's explicit approval, quoted word for word.

An approved version is never modified.
