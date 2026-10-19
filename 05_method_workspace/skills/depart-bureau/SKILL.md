---
name: "depart-bureau"
description: "When the user leaves the office or takes their computer away, and on their return: full PC ↔ cloud synchronization, autonomous and safe work in the cloud during the absence, deposit of the work onto the PC."
---

# Leaving the office, absence, return

The user often takes their computer away. During the absence, the PC is **not reachable**: no local VM, no LM Studio, no built-in browser, no backup to the PC. The work continues in the cloud, then everything is deposited on the PC on return.

## 1. Before leaving (the PC is still reachable: be quick)

Mandatory order, most critical first:

1. **Full backup cloud → PC** (skill `sync-cloud-pc`, full mode), until `N / N fichiers présents et conformes` ("N / N files present and compliant").
   - First replay the tool moves on the PC (`organiser_outils.py rejouer`) if tools have been adopted or tidied since the last backup. Otherwise, duplicates appear.
2. **PC → cloud.** From the PC manifest, list the files present on the PC and absent from the cloud. Bring back those that are used for the work:
   - the author's versions (`…a`);
   - results from the LM Studio worker (`file_lmstudio/sortie/`);
   - the PC's audits and reviews (`revues/`);
   - files added by the user in the work folders.

   They go to the same path in the cloud, without overwriting (`cp --update=none`). Do not bring back the untouchable folders (`10_revision_01.1`) or the `_copie_cloud_*` copies.
3. **Absence plan**: `00_competences_claude/taches/plan_absence_<AAAAMMJJ_HHMM>_v1.md`. It contains:
   - the tasks to continue, by priority;
   - for each one: end criterion, tools to use, what waits for the PC;
   - the maximum duration (12 h by default).
4. **Departure message**, in 3 lines:
   - the backup (`N/N conformes`);
   - what continues in the cloud;
   - what waits for the user's return (LM Studio batches, approvals).

If the PC has already left: say so, work in the cloud, and back everything up on return.

## 2. During the absence (cloud only)

**Continue without stopping**, in this order:
1. The user's ongoing tasks, for example the report.
2. The tools: missing tests, audit checks, generalizations, through the `preparer` / `adopter` cycle, tests included.
3. The classifiers:
   - retrain on the cloud CPU when the data has changed;
   - compare on the test bench;
   - record the follow-up in `entrainement/suivi/`.
4. Methodology and automation: as proposals only.
5. Technology watch on ML, classifiers and AI (WebSearch and WebFetch; the built-in browser is on the PC). It yields dated notes with their sources, then proposals.

**Safety rules.** They are not relaxed when the user is absent:
- **No self-approval.** Every improvement to a method, a skill, a lesson, the memo or a guide is deposited in `00_competences_claude/propositions_a_reviser/` and entered in its index (`INDEX_vN.md`). Skills are also presented as a card (`propose_skills`), which the user saves themselves. Lessons and the memo stay `proposés` ("proposed").
- Nothing irreversible:
  - no deletion;
  - no sending or publication;
  - no credentials entered;
  - no deliverable handed to a third party.

  A decision that can go either way waits for the return: prepare the work, set out the decision, move on to the next task.
- Never overwrite; everything is versioned in the work folders.
- No person's name in my documents.

**Rhythm.**
- Backups: the session cron task tries the quick mode; if the PC does not respond, it notes this in one line. No retry or wait: the backup state keeps what remains to be sent.
- Log: `taches/journal_absence_<AAAAMMJJ>_vN.md`, a new version at each step checkpoint. It records what is done, what is proposed and what waits for the PC.
- If the turn ends before the end of the plan: schedule a reminder in this session (`send_later`, in 30 to 60 min) that resumes the absence plan at the point noted in the log.

  Stop the reminders:
  - when the plan is finished and no useful improvement remains;
  - when the maximum duration is reached;
  - when the user returns.
- Send a message (`SendUserMessage`) only for an important result or a blocker, not for every step.

**What waits for the PC**: LM Studio batches, the daily review on the PC (its scheduled task reports that the PC is unreachable), trials in Word, deliveries on the PC.

## 3. On return

1. Check that the PC responds: a simple `device_bash`.
2. Replay the tool moves on the PC (`organiser_outils.py rejouer`). First send the tool and the move logs if they are missing.
3. **Full backup cloud → PC** (full mode).
   - A version modified by the user on the PC is never overwritten: the cloud version goes into `_copie_cloud_<date>/`.
   - End of the step: `N / N conformes` ("N / N compliant").
4. **PC → cloud**: bring back what the user added or modified during the absence (same method as at departure), then integrate it into the work.
5. LM Studio: ask the user to restart the worker if there are batches waiting, then collect the results.
6. Summary in a few lines:
   - what was done;
   - what awaits a decision;
   - the proposals to review (index of `propositions_a_reviser/`).
