# Guide to creating and updating tools (v1, 15 Oct. 2026)

**Imperative rule: everything that repeats or produces a result is automated by a reusable tool.** I do not redo by hand, with a throwaway command, what a tool does or could do.

## 1. Before programming anything: search

```
python3 outils/chercher_outil.py <mots-clés du besoin>
```

Depending on the result:

| Result | What I do |
|---|---|
| A tool does exactly what is needed | I use it, through its shortcut `python3 outils/<outil>.py …`. |
| A tool almost does it, but is not suited to my case | I **generalize** it (§ 2), instead of writing one more script alongside. |
| No tool comes close | I **create** a tool (§ 3). |

A one-off command (`python3 -c`, a script pasted into the terminal) is permitted only to **inspect**: read, count, display. As soon as it transforms data, produces a file or is used a second time, it is a tool.

A script specific to a single job goes in `NN_travail/90_scripts/`. If it is used in a second job, it becomes a tool.

## 2. Generalizing an existing tool (new version)

1. **Prepare** the next version:
   ```
   python3 outils/organiser_outils.py preparer <outil>
   ```
   It is copied from the current one, with `VERSION` and `REMPLACE` ("REPLACES") prepared. It is a **draft**: it can be modified as long as it has not been adopted.
2. **Modify while staying compatible.** The default behaviour does not change; new features go through options or new cases. Complete `REMPLACE` (what changes and why).
3. **Existing tests: they must all pass** (non-regression). The whole suite is rerun on the candidate version at step 5.
4. **Add tests for each new feature**, in a new version of the suite: `tests/test_<outil>_v(K+1).py`. It imports the previous suite, whose tests remain valid, and adds the new ones. If the tool has a test bench (`bancs/<outil>/cas_vN.py`), add the new cases in a new version of the cases.
5. **Adopt**:
   ```
   python3 outils/organiser_outils.py adopter <outil>
   ```
   The tool runs all the tests on the candidate and refuses adoption at the slightest failure. Then:
   - the old version goes into `outils/<outil>/archive/`;
   - the shortcuts and the register are updated.

   With a test bench, also run `python3 outils/banc.py <outil> --comparer N N+1`: adopt only if quality, alignment and determinism do not decrease.
6. **Regenerate the catalogue**: `python3 outils/catalogue.py`.

## 3. Creating a tool

1. Folder `outils/<outil>/`, file `<outil>_v1.py`. Standard header: `OUTIL` ("TOOL"), `VERSION`, `RESUME` ("SUMMARY"), `USAGE`, `ENTREES` ("INPUTS"), `SORTIES` ("OUTPUTS"), `CATEGORIE` ("CATEGORY"), `BANC` ("TEST BENCH"), `REMPLACE`.
2. **Dependencies**: use the other tools through their shortcut. Write `import detecteurs_rapport as DR` (current version) or `importer('outil', N)` for a specific version, rather than a frozen number. The shortcut engine makes both possible.
3. **Tests**: `tests/test_<outil>_v1.py`, with the standard library's unittest and the helper `aide_tests_vN.py`. Trials write into `tests/_test_execution/`, never into a temporary space.
4. `python3 outils/organiser_outils.py raccourcis`, then `python3 outils/tester_outils.py`, then `python3 outils/catalogue.py`.

## 4. Qualities required of every tool

- **Deterministic**: same inputs, same output. No LLM in a tool. A model judgement goes through the micro-task queue, and a developed classifier eventually replaces it.
- **Typed and versioned outputs**: never overwrite (`ecrire_versionne`, opening in mode `x`).
- **Log**: one event per run (`evenement`).
- **No person's name** in the code, the tests and the trial data: roles or fictitious names.
- **Resources**: read little, compute locally, never pass data through my replies.
- **Reusable**: paths and parameters as arguments, no value specific to a single job.

## 5. Versions: the rules

- **Adopted**: frozen, never modified. Any change creates a new version.
- **Candidate**: the highest version in `outils/<outil>/` before `adopter`. It is a modifiable draft.
- `outils/<outil>/` keeps only the current version, and `outils/<outil>/archive/` the previous ones. The main folder contains only shortcuts of constant content; no copy is duplicated.
- Test suites are versioned like the tools. A replaced suite goes into `tests/archive/`; a move made by hand is recorded with `organiser_outils.py consigner`.
- Each move is recorded in `outils/_gestion/deplacements/`. On the PC, after a backup: `python3 outils/organiser_outils.py rejouer`.

## 6. Checklist before saying "done"

- [ ] `chercher_outil` consulted before programming.
- [ ] Existing tests green, new tests written for the additions (`tester_outils`: compliant verdict).
- [ ] Test bench compared, if there is one.
- [ ] `adopter` succeeded, catalogue regenerated, `organiser_outils.py verifier` compliant.
- [ ] Quick backup done, and `rejouer` run on the PC if files were moved.
