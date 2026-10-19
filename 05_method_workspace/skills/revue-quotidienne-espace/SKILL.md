---
name: "revue-quotidienne-espace"
description: "Complete daily review (every 24 h) of the work folders and the competence workspace, as a mentor: anomalies, useless or poorly designed tools, and improvement recommendations."
---

# Daily review of the workspace (reviewer, mentor)

This review runs every day as a scheduled task, in a fresh session, or at the user's request.

**Purpose.** An outside view of my own work. It consists of:
- detecting any anomaly, for example a tool that produces `.txt` artifacts that nothing uses;
- checking the structure against the conventions and development best practices;
- checking that the tests of each tool exist and follow its versions;
- tracking from one review to the next what persists;
- proposing concrete solutions.

Two principles:
- **Change nothing.** The review touches neither the tools nor the deliverables: it records findings and recommends. Only the deterministic maintenance commands of § 3 are run. Changes are made afterwards through the cycle of the tool creation guide, or after the user's agreement.
- **Be efficient.** What was checked the day before and has not changed is not rechecked.

## 1. Getting set up

- **Work on the PC, in the local VM**, on the `Revision` folder: `cd "$HOME/mnt/Revision/00_competences_claude"`.
- If the PC is not reachable (computer taken away, switched off), say so in one line and stop. There is nothing to review without the folders.
- Read the entry point `LISEZMOI_CLAUDE_vN.md` (latest version) and the approved memo (`python3 outils/memoire.py courant`), without rereading the tools one by one.
- Read the previous review: `revues_audits_quotidiens/revue_<date>_vN.md` and its `.json` file, the most recent ones.
- Folder names: those of the registry `outils/_gestion/chemins_vN.json` (for example `revues_audits_quotidiens/`, `skills_propositions_a_reviser/`, `journal_evenements_outils/`). If the PC still carries old names, it means the recorded moves have not been replayed there: `organiser_outils.py rejouer` (§ 3) applies them, never a manual correction.

## 2. File tree at startup, and first review

First command, before any other:

```
python3 outils/auditer_espace.py --racine "$HOME/mnt/Revision"
```

The audit:
- takes the tree of files (size, date, checksum);
- compares it with the previous tree of the same workspace, kept in `revues_audits_quotidiens/arbres/arbre_Revision_<ts>.json`: additions, deletions, modifications, moves;
- re-examines only what has changed, and carries over as they are the findings for the unchanged tools and folders;
- writes `revues_audits_quotidiens/audit_Revision_<ts>.md` and `.json`, as well as its state in `revues_audits_quotidiens/etat/`.

Read **section 1** of the report first (tree and changes). This is the first review of the tree:
- folders or files outside the conventions: a folder not named `NN_sujet`, a tool file outside `outils/<outil>/`, a file placed at the root;
- unexpected deletions (none must happen without permission);
- moves not recorded in `outils/_gestion/deplacements/`;
- abnormal growth;
- temporary names.

The added, modified or moved files form **the only scope** of the mentor review (§ 5). `--complet` re-examines everything: only on Mondays, or after a new version of `auditer_espace`.

## 3. Deterministic maintenance, only if the audit asks for it

| Condition | Command |
|---|---|
| Always (cheap) | `python3 outils/organiser_outils.py rejouer` |
| A17, or changes under `outils/` | `python3 outils/organiser_outils.py verifier --ranger-vides` |
| A25 (code modified with no later test report) or A16 | `python3 outils/tester_outils.py --complet` |
| A08 | `python3 outils/catalogue.py ; python3 outils/organiser_outils.py registre` |
| Lessons modified | `python3 outils/lecons.py verifier` |

If a command was run, rerun the audit: it is incremental and takes only a few seconds. The second report shows what the maintenance resolved, and it is the one the review uses.

## 4. Structure, conventions and tests (read from the audit)

- **Structure and conventions:**
  - A23: a single current version per tool, complete header, no hard-coded absolute path;
  - A17: organization (shortcuts, `_compat`, archives);
  - A13: conventions of the work folders (LISEZMOI, deliverables 98/99, versions, non-overwriting);
  - A20: work script to be promoted to a tool;
  - A04: temporary file left behind.
- **Tests:**
  - A06: tool without tests;
  - A24: new version without a test suite added or modified since the previous one;
  - A25: tests to rerun, tracked until a later report;
  - A16: failing tests, blocking.
- **Artifacts:** A01 (unused), A02 (duplicate), A03 (empty file).
- **Method and learning:**
  - A10 and A11: approvals pending;
  - A18: stalled LM Studio queue;
  - A22: classifier to retrain;
  - A07: unused tool;
  - A12: growth of the trials or of the log.

By hand, only for the changed tools (section 1): read the CHANGELOG entry and the new test suite, not the whole tool. Check that the additions are tested.

**Known limitation.** On the PC, the backup dates the files from the time of the copy. The checks based on the date (A24, A08, A22) can stay silent there; the audit in the cloud (the "claude" workspace) remains the reference for them.

## 5. Mentor review (judgment, on the residue)

It covers at most 5 productions **changed since the previous review**: section 1 of the audit and the log of the last 24 hours (`journal_evenements_outils/AAAA-MM-JJ/`). Never reread an unchanged file: its checksum is in the tree. The questions to ask:
- **Usefulness**: does each file produced serve something or someone? An artifact that nothing reads signals a tool to revisit (useless output, or a format to change so that a tool consumes it).
- **Automation**: were there one-off commands that should have been a tool? Is a work script reused? Was a tool copied instead of being generalized?
- **Tool quality**: new tools without tests, vague headers, hard-coded paths, values specific to a single job, unversioned outputs, risk of overwriting.
- **Method**: lessons not applied, approvals pending (memo, lessons, skills), backup running late, people's names in my documents, data passing through the conversation (waste of tokens).
- **Learning**: verified judgments not added to the training directory, classifiers to retrain, micro-tasks that a rule could settle.
- **Work flow**: read the bottlenecks in the latest `revues_audits_quotidiens/tableau_de_bord/donnees_tableau_vN.json`, without regenerating it (it is produced in the cloud only: generating it on the PC would create competing versions). These are G-… findings with their proof: waiting, straggling or overloaded agents, unconfirmed backups, pending decisions, open steps. A bottleneck present in two reviews in a row becomes a recommendation. A work step not recorded in the log is also a method finding.

## 6. Follow-up log (what continues)

- **Findings**: for each one, the audit keeps its date of first appearance ("since") and lists the new and the resolved ones. A blocking or major finding that persists for more than 3 days goes to the top of the summary.
- **Recommendations**: those of the previous review are reread from its `.json`. Each receives a status, with its proof (finding resolved in the audit, or file):
  - done;
  - in progress;
  - not started;
  - abandoned, with the reason.
- New recommendations receive an identifier `R-<AAAAMMJJ>-<n>`.

## 7. Delivering the review

Write `00_competences_claude/revues_audits_quotidiens/revue_<AAAAMMJJ>_vN.md`, with `revue_<AAAAMMJJ>_vN.json` beside it: the list of recommendations `{id, code, cible, probleme, solution, commande, statut, depuis}`. Both are versioned and never rewritten.

Sections of the report:
1. **Summary** in 3 lines: general state, number of blocking and major findings, trend (new, resolved) since the previous review.
2. **Tree**: what changed, and structure anomalies seen in the tree.
3. **Problems found**: blocking and major, new ones first, then persistent ones with their age, each with its proof (path, audit finding).
4. **Potential solutions and prioritized recommendations.** Table: identifier, problem, solution, tool or folder, effort, gain, command (for example `organiser_outils.py preparer <outil>`).
5. **Follow-up of the previous recommendations.** Table: identifier, status, days, proof.
6. **Proposals for lessons, rules or new audit checks.** These are proposals: the user validates them.
7. **To be approved by the user.**

Then send the user a short message: the summary, the 3 main recommendations and the path of the file.

## 8. Improving the review itself

- Any anomaly found by hand twice becomes a check of `auditer_espace`, through the `preparer` / `adopter` cycle, with a test for the new check.
- The review itself approves nothing: method improvements go into `00_competences_claude/skills_propositions_a_reviser/`.
