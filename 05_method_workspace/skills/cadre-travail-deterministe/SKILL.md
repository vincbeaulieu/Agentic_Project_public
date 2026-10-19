---
name: "cadre-travail-deterministe"
description: "Mandatory framework for all work done for the user: folders, strict naming and versions, deterministic evaluation, evaluated delegations, local micro-tasks in a queue, developed classifiers, competence workspace, step log and dashboard."
---

# Deterministic working framework

## Why

Models introduce randomness. This framework reduces it:
- written rules are **checked by deterministic scripts** (hard rules, instant categorization, typed outputs), not by an LLM's judgment;
- each skill acquired is carried by a **versioned tool**, whose performance is **measured and compared** from one version to the next;
- **everything redundant is automated** (lesson LC-015), **reusing first**: a repeated need is handed to the tool that already covers it, or to a new version of that tool; a new tool is written only if none does the job (§ "Tools: reuse first, call through the shortcut"). This applies to tools, to the micro-task queue and to the **classifiers that I develop myself**: ML development is part of tool creation, and no classifier is handed over ready-made;
- **what explains is not necessarily what causes** (LC-036): a diagnosis remains a hypothesis until the source has confirmed it (§ "Diagnosing").

## Names of people

No person's name appears in my own documents: skills, competences, memory, rules, lessons, briefs, folders, scripts, training data. I write "the user" (or the administrator, the end user) and "colleague" ("Colleague A", "reviewing colleague").

Documents delivered to the user keep the original names.

Check: `outils/detecter_noms.py` (checksums, no plain-text list). To create a version without names: `outils/anonymiser.py` (roles from `regles_travail/roles_vN.json`), which writes the file `_v(N+1)`.

## The competence workspace

It is located in `/home/claude/00_competences_claude/` (on the PC: `Revision\00_competences_claude\`).

**Central path registry.** Each folder is designated by a logical key, whose real name is read from `outils/_gestion/chemins_vN.json`: `chemin('lecons', …)` of the common library (`from cc_lib_v5 import chemin`; since v5, a wrong root makes the import fail instead of returning empty folders). No tool hard-codes a folder name; the check is done by `delegations_agents/verifier_chemins_en_dur_v2.py` (a script still outside `outils/`, to be promoted). A folder is renamed as follows:
1. new version of the registry;
2. recorded move (`organiser_outils.py consigner`);
3. replay on the PC (`organiser_outils.py rejouer`).

No new tool version is needed.

| Element (key) | Role |
|---|---|
| `LISEZMOI_CLAUDE_vN.md` | Entry point: protocol, rules, commands |
| `memoire_methodologique/MEMOIRE_METHODOLOGIE_vN.md` (`memoire`) | Methodology memo, versioned; only the latest **approved** version is authoritative |
| `catalogue_outils/catalogue_outils_vN.md` (`catalogue`) | **Tool dictionary**, generated from the tools' headers: there is no need to reread each tool |
| `outils/<outil>/` | Current version of each tool (`<outil>_vN`), previous versions in `archive/`, draft in progress in `candidat/` (never run by the shortcuts); `outils/<outil>.py` is a shortcut to the current version |
| `skills_propositions_a_reviser/` (`propositions`) | Everything awaiting the user's decision, and the audit of proposals (`outils/suivre_propositions.py`) |
| `skills_atelier_de_propositions/` (`skills_atelier`) | Complete drafts of the skills I write, one version per file |
| `skills_ressources_par_skill/` (`skills_ressources`) | Skill resources: older versions, reference scripts, examples |
| `regles_travail/regles_travail_vN.json` (`regles`) | Rules O, E, N, K, D and L3, checked by `evaluer_travail` |
| `lecons_apprises/registre_lecons_vN.md` (`lecons`) | Lessons (one immutable JSON file per lesson and per version), each linked to its check |
| `delegations_agents/`, `taches_types_automatisables/` | Delegations, measured results; automatable steps by task type, planner, absence plans |
| `bancs_essai_outils/<outil>/cas_vN.py` (`bancs`) | Fixed cases; `resultats/`: performance by version |
| `tests_outils/` (`tests`) | Unit and integration tests (`test_<outil>_vK.py`), reports |
| `entrainement_classifieurs/` (`entrainement`) | Classifier training directory: task specifications, labeled data (immutable batches), embedding cache, models and checkpoints, test benches (`LISEZMOI_entrainement_vN.md`) |
| `revues_audits_quotidiens/` (`revues`) | Audits, daily reviews, dashboard (`tableau_de_bord/`) |
| `journal_evenements_outils/AAAA-MM-JJ/` (`journal`) | One immutable event per tool run (learning trace), and the work steps |

## At the start of each session

1. **Restore the workspace if it is missing from the cloud.**
   - List `Revision\00_competences_claude` on the PC (`device_list_dir`, recursive), then retrieve it with `device_stage_files`, in batches of 50.
   - Put it back in `/home/claude/00_competences_claude/`.
   - Check: `python3 outils/catalogue.py` must find the tools.
2. **Read the approved memo**: `python3 outils/memoire.py courant`. If there is none, apply the user's instructions and remind them that approval is pending.
3. **Read** `LISEZMOI_CLAUDE`, the latest `catalogue_outils` and the latest `registre_lecons`, without rereading the tools.
4. **For new work**, create the folder with `creer_travail`, never by hand:
   ```
   python3 outils/creer_travail.py /home/claude NN_sujet --sujet "…" --version-cible <version attendue> --source <fichiers>
   ```
   The expected version is given in the paragraph "Naming and versions".
   Options: `[--couverture a b] [--relecteurs "A;B"]`. In `TRAVAIL_vN.json`, reviewers are given by checksum (`auteurs_relecteurs_empreintes`), never in plain text.
5. **Open the work step** in the step log (§ "Progress tracking").

## Mandatory organization of a work folder

```
NN_sujet/
  LISEZMOI_vN.md, TRAVAIL_vN.json
  00_sources/                 reçu tel quel, lecture seule, sha256_sources_vN.txt
  01_… à 89_…                 étapes dans l'ordre
  90_scripts/                 scripts propres au travail
  95_journal/                 audit_vN.md, manifestes/, evaluations/
  98_livrables/               final, lecture seule, empreintes_livrables_v<version>.txt
  99_livrables_modifiables/   copies modifiables par l'usager
```

Throwaway trials go in a `_essais/` or `essais/eN/` subfolder (exempt from versioning).

## Naming and versions (strict format)

| Case | Format |
|---|---|
| Any file | `nom_vN.ext`, or a timestamp `nom_AAAAMMJJ_HHMM[SS].ext` |
| Document revision | `Nom_vX.Y.N` + `c` (Claude) or `a` (author), N increasing |
| Deliverable | `Nom_v<version>[_variante].ext`. The version is recorded in `TRAVAIL.version_cible`. It is the user's rule or decision specific to the document, recorded in `TRAVAIL.decision_version` (report: source v6.0.4-rev1 → v6.0.5-rev1); otherwise v(X+1).0.0, X being the initial version of the source. Never a "next free major version". The version is computed by `version_attendue` of the common library and checked by `evaluer_travail` (N3) and `livrer` |
| Tool | `outil_vN`: versioning specific to tools, unchanged; the report rule does not apply to it |

There is never any overwriting, including for a tool I have just written: any modification gives a new version. The successive checksum manifests prove it (rule E5).

## Delivery: always through the tool, always evaluated

```
python3 outils/livrer.py <dossier> <fichier>:<Nom>[:<variante>] …
```

The tool names the files, protects them, computes the checksums, creates the editable copies, then runs the evaluator.

The default evaluator for any deliverable is the current version of `evaluer_travail`: `python3 outils/evaluer_travail.py <dossier>`. It checks:
- the organization (O);
- integrity and non-overwriting (E);
- naming (N);
- Claude's comments (K): short, starting with `Fait :` ("Done:"), `Proposition :` ("Proposal:"), `Données :` ("Data:") or `Question :` ("Question:");
- the Word deliverable (D): XSD, comments kept, rejecting the pass = source, cover page, a single new author;
- the reviewing colleagues' revisions kept (L3).

**The `CONFORME` (compliant) verdict is required before any delivery.** It is also run at the end of each step.

To revise a Word report, add `outils/detecteurs_rapport.py`, before and after:
- DR-01: orphan references;
- DR-02: broken cross-references;
- DR-03: unique information deleted;
- DR-04: typography;
- DR-05: lists;
- DR-06: term variants;
- DR-07: replacement request not satisfied;
- DR-08: a colleague's suggestion half-neutralized (their insertion deleted, their deletion left in place: a hole on acceptance);
- DR-09: broken text in the accepted view (determiner followed by punctuation, fragment glued at the end of a paragraph, word glued after a period).

A new DR-08 or DR-09 blocks delivery (LC-017). For requests, `outils/croiser_demandes.py` crosses the type of each request with what the pass actually did (LC-008, LC-009). `outils/dossier_ecarts.py` draws from it the judgment files by section: word-by-word difference, lost information, text taken up elsewhere, summary of verdicts.

Formatting is checked on the **accepted view** (LC-019): `outils/controler_mise_en_forme.py comparer <avant> <après> --auteur "<passe>"` reports, with the author of the revision that introduced them, sizes outside the body text (MF1, MF2), Markdown (MF3), empty lines and paragraphs (MF4, MF5), orphan fragments (MF7), merges that turn a heading into body text (MF8) and emptied tables or tables without a caption (MF9, MF10). A new gap from the pass blocks delivery. Unambiguous corrections are made as tracked changes by `outils/harmoniser_mise_en_forme.py`. The D3 check of `evaluer_travail` ("rejecting the pass = source") also covers tracked formatting.

## Verified delivery (LC-018)

Nothing is announced as working before it has been run under the conditions of its real use:
- same system, same interpreter and same version (PowerShell 5.1 under Windows, Word); failing that, the closest equivalent in the cloud (pwsh, real acceptance by LibreOffice) **and** an acceptance test run on the user's side;
- real installation path: the source copy is never the execution copy;
- real data, all modes, languages and time zones concerned.

The acceptance test done on the PC is recorded as a step in the log. When only the user can do it, the delivery message says so, gives the procedure in a few lines, and does not present the deliverable as verified.

## Diagnosing: hypothesis or finding (LC-036)

*Moral*: what explains is not necessarily what causes. An explanation that fits the symptom remains a **hypothesis** until the source has confirmed it, even when I am the one putting it forward, and even when I blame myself. (Story, 16 Oct. 2026: a tool answers "0"; I blame the tool, wrongly; then myself alone, half wrongly; both times announced as a fact.)
- I say "hypothesis" to the user until it is verified; "finding" only afterwards.
- I verify through the tool's normal call, in the source (files, independent counts), and I watch the symptom disappear after the fix; if it remains, there is another cause.
- A duration, a date, a number are computed before being written (timestamps, `date`, numeric sorting of versions rather than alphabetical).
- "Fixed" means **in service and verified**, not "fix written".

## Reported defect: corrective approach (LC-020)

When the user reports a defect in a deliverable:
1. **Investigate** the cause and the provenance (author, version, mechanism) with a deterministic tool, going back through the version history.
2. **Present** the findings.
3. **Plan** the fix in a versioned plan in the folder (rules, number of fixes, cases left to decision).
4. **Test**: unit tests with a control (without the fix, the test fails), a trial on the real document, a check against the target environment.
5. **Present** the plan and the results, with the decisions to be made.
6. **Apply only after agreement**, in a new work folder and a new version; the approval is quoted word for word in `TRAVAIL` (`approbation_plan`).
7. **Learn**: tools (new versions), lesson and skills affected, as proposals.

## Local models: micro-tasks in a queue

What a tool cannot yet judge is split into micro-tasks: a closed question, a short input, a JSON output with permitted values. Tool: `outils/microtaches.py`.

- **Token-free transport (LC-016).** The payload never passes through my replies. `outils/file_lmstudio.py` is launched on the PC, in the local VM. It drops the batches in `Revision\00_espace_cloud_claude\file_lmstudio\entree\` and then collects `sortie\`. The Windows worker `worker_lmstudio` has LM Studio process them (see the README of the folder).
- **Scheduler.** Priorities from 0 to 3, with aging: no starvation. Tasks for the same model are grouped, to limit context switches.
- **Never wait.** I drop the batch, do something else, then collect.
- **Measure first.** A pilot on a stratified reference sample measures, per model: accuracy, F1, ms, consistency between passes.
- **Deterministic rules applied after the model** (`microtaches combiner`). Examples: replacement markers → `modifier` ("modify"); missing references or numbers → `partiel` ("partial") at most.

## Classifiers: ML development of my tools

A classifier is a tool that I write, train, measure and version like any script. Its purpose is to take over, case by case, the repetitive judgments handed to local models and then to agents.

- **Code.** `outils/entrainer_classifieur.py` produces the features (hashed n-grams, pair features, cached embeddings) and trains a softmax regression or a perceptron (Adam, weights by quality and by class). My tools can be written in Python, JS, Node, TypeScript, Go… depending on the need.
- **Training directory** (`entrainement_classifieurs/`), fed **at every job** by `outils/donnees_entrainement.py collecter`:
  - gold: the user's corrections, my verified judgments (pilot references, control sample, residue verdicts);
  - silver: local model + rules;
  - bronze: rule alone.
- **Compute.** On CPU (numpy, Claude's cloud or the PC's VM) when the GPU is absent or taken by LM Studio. The torch engine (cpu or cuda) is used when a GPU is free.
- **Portable checkpoints** (`ckpt_eNNNNN.npz`). Each contains:
  - the parameters;
  - Adam's moments and the time step;
  - the epoch;
  - the random generator state;
  - the data checksum.

  `--reprendre` restarts from where the training stopped, on any engine. Resumption is bit-for-bit identical on the same engine (resume test bench).
- **Evaluation on gold only**, in cross-validation. **Adoption** if the accuracy equals or exceeds that of the baseline (rules + best local model) on the same examples.
- **Routing.** The confidence threshold is computed for a target precision. Above the threshold, the decision is made without an LLM; below it, a micro-task goes into the queue, and its answer comes back as an example.

## Delegating

Every delegation has:
- a **typed output**;
- a **deterministic evaluator**, which the agent runs until `BILAN conforme` ("compliant result") and which **I rerun myself**;
- a record created with `outils/delegation.py ouvrir`, then a `resultat` per agent, with the measurements.

**Performance** is read on seven dimensions measured separately:
- alignment;
- quality;
- speed;
- resources used (including tokens);
- resources consulted;
- compactness;
- share of deterministic automation.

Each task type (`taches_types_automatisables/`) lists its automatable steps. As soon as a step can be done without an LLM, it goes through a tool: the one that already covers it (catalogue first), otherwise a new version of the closest tool, and as a last resort a new tool.

**Agent load.** Sub-agents draw from the same token pool as I do. I give them small, balanced batches, and short briefs that point to the tools and skills rather than copying their content. I treat them as student agents: clear instruction, tools to use, evaluator to run. The dashboard measures each agent (duration, maximum context, tokens) and flags high loads (G-AG2) and unbalanced waves (G-AG1).

**Staying reachable.** The user's messages arrive with the result of the next tool call. I work in short calls, and I read messages between two steps. The org chart is approved before any agent launch (skill `orchestration-agents-recursive`).

## Progress tracking: step log and dashboard

The user follows my work and spots bottlenecks on the dashboard (`outils/tableau_de_bord.py`).
- **Steps.** Each work step is recorded in the log:
  - at the start: `etape debut <id> --titre "…" --categorie rapport|outils|revue|sync|agents|autre`;
  - at each intermediate result: `etape point <id> --note "…"`;
  - at the end: `etape fin <id> [--resultat ok|partiel|echec]`.

  A wait (PC unreachable, user decision, agents, LM Studio) is recorded by `etape attente <id> --titre "…" --raison pc|utilisateur|agents|lmstudio`, and closed as soon as it is lifted. Steps reconstructed after the fact are imported with `importer_etapes` and marked as such.
- **Planner.** Every scheduled task, session cron task, worker or reminder (`send_later`) is recorded in `taches_types_automatisables/planificateur_vN.json` (new version at each change).
- **Dashboard.** `tableau_de_bord.py generer` aggregates:
  - the tool log;
  - the steps;
  - the agents, read from their transcripts (incremental cache);
  - the planner;
  - what is waiting.

  It applies the bottleneck rules G-… and writes a versioned page. I republish it at the same artifact URL (`revues_audits_quotidiens/tableau_de_bord/artifact_vN.json`) at the end of each step. It is generated in the cloud only, where the agents' transcripts are: generating it on the PC would create competing versions.

## Tools: reuse first, call through the shortcut

**Before writing a script or a tool**, including a project script in `90_scripts/`, and including when a built-in skill (docx, pptx, xlsx, pdf) says to write a script:
1. `python3 outils/chercher_outil.py <mots-clés du besoin>` (the catalogue must be up to date: `python3 outils/catalogue.py` after each adoption);
2. as long as the search does not index scripts outside `outils/`, also search the project scripts and the skills' resources (`grep -rl <mot> /home/claude/*/90_scripts /home/claude/00_competences_claude/skills_ressources_par_skill`);
3. decide: the tool exists → use it; it nearly does the job → new version (§ "Improving a tool"); nothing does it → create;
4. every new script or tool carries at the top the line `CATALOGUE CONSULTÉ : <requête> → <résultat>` ("catalogue consulted: query → result").

**Three levels of tools** (pilot approved by the user on 16 Oct. 2026, on the delivery chain of a docx):

| Level | Role | Rule |
|---|---|---|
| Founders | libraries on which everything depends (common library, shortcuts, test helper) | a failure there silently contaminates everything: loud failure, full suite at every change |
| Base | one precise problem, one input, one output (`detecter_noms`, `controler_mise_en_forme`, `docx_couches`…) | called through its shortcut; unit and negative tests; merged only with a tool that does the same job |
| Procedures | chain base tools (`livrer`, `evaluer_travail`, `organiser_outils adopter`) | no logic of their own: shortcut calls, gates, report; the judgment steps (looking at pages and images) are declared checkpoints; one negative test per gate; created only for a chain already repeated at least twice |

A split tool is often preferable: distinguish a tool's **role** from a **sequence of steps**. Do not absorb into a tool a step that a tool or a procedure already does: that would recreate a piece of an existing flow.

**Call through the shortcut, always**: `python3 outils/<outil>.py …` from `00_competences_claude/`.
- Never a tool's `_vN.py` file, never `PYTHONPATH` pointing to `outils/`, never a draft from `candidat/` outside the `preparer` / `adopter` cycle (to try a draft: `python3 outils/tester_outils.py --outil <outil> --candidat <outil>=N`).
- A test suite on its own: `python3 outils/tester_outils.py --outil <outil>`.
- An import error, a refusal or an unexpected message is **information about my call**: I read the message and fix the call; I do not work around it.
- An empty or null result ("0", "{}", empty list) is checked against an independent count in the source (ls, grep) before being believed.

## Improving a tool

Follow the guide `guides_methode/GUIDE_creation_outils_vN.md` and the previous section: look for an existing tool first, and generalize it rather than creating another.
1. `python3 outils/organiser_outils.py preparer <outil>`: writes the draft `outils/<outil>/candidat/<outil>_v(N+1).py`, without ever editing an adopted version. A shortcut never runs a draft. The header is standard: `OUTIL`, `VERSION`, `RESUME`, `USAGE`, `ENTREES`, `SORTIES`, `CATEGORIE`, `BANC`, `REMPLACE`. Folders are designated by `chemin(clé)` of the common library (`cc_lib_v5`).
2. Add a test suite for the additions (`tests_outils/test_<outil>_v(N+1).py`, which replays the previous one and checks the tool in a workspace with renamed folders) and, if needed, the test bench cases (`bancs_essai_outils/<outil>/cas_vN.py`, authors designated by their role). `python3 outils/banc.py <outil> --comparer N N+1`: F1, share of exact cases and determinism must not drop.
3. `python3 outils/organiser_outils.py adopter <outil>`: puts the draft in place, runs the tests (and puts it back in `candidat/` if they fail), archives the previous version, updates shortcuts and registry. If tests unrelated to the tool fail, prove their independence (they also fail with the current version), adopt with `--sans-tests` and note it in the step, and fix the fragile test in its own new version (a test that depends on today's date is a defect of the test).
4. Regenerate `outils/catalogue.py`, then `outils/bilan_competences.py`.

## Learning

**What a lesson is.** It is the moral of the story: what an experience made me understand, said simply enough and broadly enough to guide me in a situation I have not yet lived. It changes my judgment, not just my action. A rule or a procedure says what to do in a known case; a tool or a guard enforces it; a lesson makes me understand why. A routing datum ("this task type: never that model") is not a lesson: it goes to the register or to the routing table.

A lesson has four parts:
1. **the story**: what happened, in a few lines, with the proof;
2. **the moral**: one sentence, general, easy to remember;
3. **what I will do differently**;
4. **how we will see that I have learned it**: an observable sign (no more recurrence, no more correction in front of the user…).

A lesson can be improved. Several lessons that tell the same story are consolidated into a single, deeper one, with the user's agreement.

**When an error comes back**, I first look for what teaches it to me (my own texts: skills, LISEZMOI, guides, lessons, handover notes) before counting on my vigilance, and I fix that text. *I redo what I was taught to do.*

- **A lesson**: a JSON file in `lecons_apprises/saisies/`, then `python3 outils/lecons.py ajouter <fichier>` and `lister`.
  - A lesson stays `proposée` ("proposed") until the user has validated it.
  - `lecons.py verifier` lists the validated lessons that do not yet have an automatic check: this is the automation work list.
- **Every verified judgment** (mine or the user's) also enters the training directory, as a gold example.
- **The skills affected by a lesson** are updated by `propose_skills`, with the complete SKILL.md. The lesson lists the passages it modifies (skills, LISEZMOI, guides); until they are updated, it is not propagated.
- **The methodology memo** evolves through a new version: `memoire.py proposer`, then `approuver` only after the user's explicit agreement, quoted word for word.
- **No self-approval.** Every improvement to a method, skill, lesson, guide or to the memo is deposited in `skills_propositions_a_reviser/`. Its events (proposed, modification requested, accepted…) are recorded by `outils/suivre_propositions.py`.

## Backup

Skill `sync-cloud-pc`: the GitHub relay sends everything to the PC every 10 minutes, with no intervention, and I check its receipts; the full mode (PC manifest) remains the safety net, at the end of each step and before a departure. Claude's cloud may be used freely as long as these synchronization rules are respected. The competence workspace, training directory included, is backed up like any `NN_…` folder. After an adoption, a tidy-up or a renaming of a folder, `organiser_outils.py rejouer` is run on the PC before the backup. Each backup is a `--categorie sync` step in the log.
