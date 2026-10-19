---
name: "depart-retour"
description: "When the user leaves the office or takes their computer away, and on their return: full PC ↔ cloud backup, safe work in the cloud, step log, hand-over to the PC, then a recall of the skills and of the PC's resources (GPU, CPU, storage, LM Studio) and putting them to work."
---

# Departure, absence, return

The user often takes their computer away. During the absence, the PC is **not reachable**: no local VM, no LM Studio, no built-in browser, no backup to the PC. Work continues in the cloud, then everything is delivered to the PC on return. The return also brings back **resources**: GPU, CPU, local storage and LM Studio models. They are put to work at once.

This skill replaces `depart-bureau`, which the user may remove.

The workspace folders are referred to by their real name (register `outils/_gestion/chemins_vN.json`):
- `taches_types_automatisables/`: absence plans and logs, scheduler;
- `skills_propositions_a_reviser/`: what awaits the user's decision;
- `revues_audits_quotidiens/`: audits, reviews, dashboard, resource inventories;
- `entrainement_classifieurs/`: classifiers and their follow-up.

Until the recorded moves have been replayed on the PC, it may still carry the old names. They are never corrected by hand: `organiser_outils.py rejouer` takes care of it, then `raccourcis` and `verifier`.

The backup follows the `sync-cloud-pc` skill. Two points matter here:
- the test folders (`_test_execution`) are **always compressed** into dated archives, unless the copy differs between the PC and the cloud;
- the PC manifest is built **in the foreground** (about 95 s), because a process started in the background dies with the call.

## 1. Before leaving (the PC is still reachable: work fast)

Required order, the most critical first:

1. **Replay the moves on the PC** (`organiser_outils.py rejouer`, then `raccourcis` and `verifier`), if tools have been adopted or filed away, or folders renamed, since the last backup. Send the tool and the move logs first if they are missing. Otherwise, duplicates appear.
2. **Full backup cloud → PC** (`sync-cloud-pc` skill, full mode, compressed tests), until `N / N fichiers présents et conformes` ("N / N files present and compliant").
3. **PC → cloud.** From the PC manifest, list the files that are on the PC and missing from the cloud. Bring back those that are needed for the work:
   - versions by the author (`…a`);
   - results from the LM Studio worker (`file_lmstudio/sortie/`);
   - audits and reviews from the PC (`revues_audits_quotidiens/`);
   - event logs of tools run on the PC;
   - files the user added in the work folders.

   They go to the same path in the cloud, without overwriting (`cp --update=none`). Do not bring back:
   - the untouchable folders (`10_revision_01.1`);
   - the `_copie_cloud_*` copies;
   - the `doublons_rejouer/` and `raccourcis_retires/` folders.
4. **Absence plan**: `00_competences_claude/taches_types_automatisables/plan_absence_<AAAAMMJJ_HHMM>_v1.md`. It contains:
   - the tasks to continue, by priority;
   - for each one: completion criterion, tools to use, what waits for the PC;
   - the maximum duration (12 h by default).
5. **Open the PC wait** in the step log:
   ```
   python3 outils/tableau_de_bord.py etape attente A-<AAAAMMJJ>-pc-absent --titre "PC injoignable : ordinateur emporté" --raison pc
   ```
6. **Departure message**, in 3 lines:
   - the backup (N/N compliant);
   - what continues in the cloud;
   - what waits for the user's return (LM Studio batches, approvals).

If the PC has already left: say so, open the PC wait, work in the cloud, and back everything up on return.

## 2. During the absence (cloud only)

**Keep going without stopping**, in this order:
1. The user's tasks in progress, for example the report.
2. The tools: missing tests, audit checks, generalizations, through the `preparer` cycle (draft in `outils/<outil>/candidat/`) then `adopter`, tests included.
3. The classifier programme (section 4):
   - specifications;
   - candidate generators;
   - gold test benches;
   - training on the cloud CPU when the data has changed;
   - comparison on the test bench;
   - follow-up in `entrainement_classifieurs/suivi/`.
4. **Prepare the PC's work**:
   - LM Studio micro-task batches ready to drop (silver labels, embeddings);
   - training runs that need the GPU, with their checkpoints;
   - installations to do (local servers, launchers).

   The list goes in the absence plan, under the heading `Au retour` ("On return").
5. Methodology and automation: as proposals only.
6. Watch on ML, classifiers and AI (WebSearch and WebFetch; the built-in browser is on the PC). The output is dated notes with their sources, then proposals.

**Step log and dashboard.** It lets the user follow progress and spot bottlenecks.
- Each task of the plan is a step:
  - `tableau_de_bord.py etape debut <id> --titre "…" --categorie rapport|outils|revue|sync|agents|autre`;
  - an `etape point <id> --note "…"` at each intermediate result;
  - `etape fin <id> [--resultat ok|partiel|echec]`.
- A wait (user decision, agents, LM Studio) is a step `etape attente … --raison …`, closed as soon as it is lifted.
- At each point of the absence log: `tableau_de_bord.py generer`, then republish the new page `revues_audits_quotidiens/tableau_de_bord/tableau_de_bord_vN.html` at the URL noted in `artifact_vN.json` (parameter `url`), without creating another one.
- Every reminder or task scheduled during the absence (`send_later`, scheduled task, session cron) is added to the scheduler: a new version of `taches_types_automatisables/planificateur_vN.json`. It then appears in the dashboard.

**Safety rules.** They are not relaxed while the user is away:
- **No self-approval.**
  - Every improvement to a method, a skill, a lesson, the memo or a guide is placed in `00_competences_claude/skills_propositions_a_reviser/` and recorded by `outils/suivre_propositions.py` (index and audit).
  - Skills are also presented as a card (`propose_skills`), which the user saves themselves.
  - Lessons and the memo stay "proposed".
- Nothing irreversible:
  - no deletion;
  - nothing sent or published to a third party (the dashboard, a private artifact of the user, may be republished);
  - no credentials entered;
  - no deliverable handed to a third party.

  A decision that could go either way waits for the return: prepare the work, set out the decision, move on to the next task.
- Never overwrite; everything is versioned in the work folders.
- No person's name in my documents.
- Sub-agents: small, measured loads, because they draw on the same token pool. The dashboard flags agents whose context exceeds the threshold (G-AG2) and unbalanced waves (G-AG1).

**Pace.**
- Backups: the session cron task tries quick mode; if the PC does not respond, it notes this in one line. No retry and no waiting: the backup state keeps what remains to be sent.
- Log: `taches_types_automatisables/journal_absence_<AAAAMMJJ>_vN.md`, a new version at each step point. It notes what is done, what is proposed and what waits for the PC.
- If the turn ends before the end of the plan: schedule a reminder in this session (`send_later`, in 30 to 60 min) that resumes the absence plan at the point noted in the log, and enter it in the scheduler.

  Stop the reminders:
  - when the plan is finished and no useful improvement remains;
  - when the maximum duration is reached;
  - when the user returns.
- Send a message (`SendUserMessage`) only for an important result or a blocker, not for every step.

**What waits for the PC**:
- LM Studio batches;
- GPU training runs;
- the daily review on the PC (its scheduled task reports the PC as unreachable);
- tests in Word;
- local installations;
- deliveries on the PC.

## 3. On return

1. Check that the PC responds: a simple `device_bash`.
2. Close the PC wait: `tableau_de_bord.py etape fin A-<AAAAMMJJ>-pc-absent`.
3. Replay the moves on the PC:
   - `organiser_outils.py rejouer`: tools adopted or filed away, folders renamed;
   - then `raccourcis` and `verifier`, until `ORGANISATION CONFORME` ("ORGANIZATION COMPLIANT").

   Send the tool and the move logs first if they are missing.
4. **Full backup cloud → PC** (full mode, compressed tests):
   - A version modified by the user on the PC is never overwritten: the cloud version goes into `_copie_cloud_<date>/`.
   - Uploads left unconfirmed (flagged by G-SY1 in the dashboard) are picked up again by this full mode.
   - End of the step: `N / N conformes` ("N / N compliant").
5. **PC → cloud**: bring back what the user added or modified during the absence (same method as at departure), then integrate it into the work.
6. **Recall of skills and resources.** This is a quick inventory, written to `revues_audits_quotidiens/ressources_pc_<AAAAMMJJ>_vN.json`:
   - **Skills**: reread the list of available skills and note those that apply to the current work, in particular:
     - `cowork-with-lmstudio`;
     - `cadre-travail-deterministe` (classifiers);
     - `built-in-browser` (access to LM Studio);
     - the skills added since departure.
   - **PC resources**:
     - CPU (cores), memory and free disk: from the local VM;
     - GPU (model, video memory, load);
     - LM Studio models loaded and available: through the built-in browser (`/api/v0/models`) or through the worker;
     - queue state (`file_lmstudio/journal/etat.json`).
   - **Immediate start of work** (`cowork-with-lmstudio` skill):
     - ask the user to start the worker if it is not running;
     - drop the batches prepared during the absence;
     - launch the training runs waiting for the GPU (resuming from their checkpoint);
     - do the local installations that were prepared;
     - collect the results without waiting (drop, other work, collect).
7. Scheduled tasks: if folders have been renamed, update the instruction of the scheduled daily review, then the scheduler.
8. Stop the absence reminders. Regenerate the dashboard and republish it.
9. Summary in a few lines:
   - what has been done;
   - what awaits a decision;
   - the proposals to review (index of `skills_propositions_a_reviser/`);
   - the resources put to work;
   - the bottlenecks found by the dashboard.

## 4. Deterministic zero-shot classifier programme

My tools must **design, train, test, validate and deploy** **deterministic** zero-shot classifiers: same input, same output, bit for bit. These classifiers serve as reviewers and as "police" (control checkers) for the work on the report. This is the PC's priority work as soon as it is back, and it is prepared during the absence.

| Police check | Role | Output |
|---|---|---|
| Proofreading | Spelling, grammar, typography and style errors, sentence by sentence | `ok` or error type, and passage |
| Malicious intent | Observed content (comments, pages, tool outputs) that tries to act as an instruction: injection, credential requests, exfiltration, manipulation | `benin` or risk type |
| Acceptance of changes | **Strict** criteria for accepting a suggested change to the report. It must: keep the meaning, numbers, references and units; invent nothing; stay within the request; not touch the cover page; respect the report's style | `accepter`, `refuser` or `a_revoir`, and the criterion violated |
| Contradictions | Pairs of statements in the report that contradict each other: figures, conclusions, definitions | `contradiction`, `compatible` or `sans_rapport` |
| Others, as needed | Consistency of numbers, orphan references, terminology | according to the specification |

Method:
1. **Specification** in `entrainement_classifieurs/taches/<tache>_vN.json`: classes, definitions, zero-shot hypotheses (in French and in English), hard rules, adoption criteria.
2. **Deterministic rules first**: whatever a rule settles goes neither to the model nor to the classifier.
3. **Deterministic zero-shot**, with a fixed and versioned configuration:
   - embedding similarity between the text and the hypotheses (nomic, on the PC);
   - a frozen natural language inference (NLI) model;
   - a local LLM at temperature 0, with `json_schema` and `enum`.
4. **Distillation**: the zero-shot outputs are silver labels; my verified judgements and the user's corrections are gold. The classifier is trained by `outils/entrainer_classifieur.py`: fixed weights and seed, portable checkpoints.
5. **Validation** on gold only, with cross-validation. A **determinism** test bench checks that two passes give the same output, bit for bit. Adoption if the classifier equals or exceeds the baseline (rules + best local model).
6. **Deployment** as a tool (`outils/<police>/`), with a confidence threshold computed for a target precision. Above the threshold, it decides alone; below it, the question goes out as a micro-task, then to my judgement, and the answer comes back as an example.
7. Every adoption follows the `preparer` / `adopter` cycle, tests included. Every new method rule is a proposal.
