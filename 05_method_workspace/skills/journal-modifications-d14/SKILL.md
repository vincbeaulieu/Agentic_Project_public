---
name: "journal-modifications-d14"
description: "Produces the modification log in D14 format for a Word revision made with tracked changes: for each operation, problem, additional information, solution and why, deleted or kept passage, original text preserved, in md and docx. Use whenever a report revision must be traced or justified (log, or traceability of corrections, \"why this change\"), even if \"D14\" is not named."
---

# Modification log (D14 format)

This skill is for keeping the log of any revision of a Word document made with tracked changes: moves, deletions, rewordings, insertions and replies to comments. Each change is justified there in the format set by the user, author of the report (14 Oct. 2026).

The reviewer must be able to understand, without opening the Word file, what changed, why, and where the information now is. A log reconstructed after the fact is vague and unverifiable. This is why each entry is created when the operation is planned, not after it is applied.

## 1. The expected format (the author's words)

The author mainly expects:

> **Problem**: partial repetition with addition of information not mentioned previously.
> **Additional and complementary information not present**: "…" [the new info].
> **Solution and why**: moved to S.1.3, the new content kept as is; replacement (or combination) of the section "…" of S.1.3 by (or with) the section of the new info "…", because better worded (or more precise). Passage "…" deleted because redundant, less formal and less precise than the existing passage "…" of S.1.3.

### Entry template

```
#### <id> · <section où l'opération s'applique> · <type d'opération>
*Mandat* : <fil Fnnn (auteur : « extrait »)> ; <segment Txx (horodatage, thème)> ; <décision Dn>. *Justification* : <commentaire | restructuration | redondance | résidu | renvoi>.
- **Problème** : …
- **Information additionnelle et complémentaire non présente** : « … » (ou « aucune ; … » pour une redondance pure)
- **Solution et pourquoi** : <ce qui est fait>. <pourquoi : mieux formulé, plus précis, demandé par…>
- **Modification** : « ancien » → « nouveau »   (une ligne par remplacement)
- **Passage supprimé** : « … »
- **Passage gardé** : « citation exacte » — <lieu> (¶ <paraId>)
- **Revue C5** : <où vit chaque élément du passage supprimé qui n'est pas dans le passage gardé>
- **Texte d'origine** : N des M mots du paragraphe conservés (P %)
```

For a move, replace `Modification` ("Change") with **`Texte déplacé`** ("Moved text") (excerpt, number of paragraphs), with the line `Texte d'origine : 100 % (déplacé tel quel)` ("Original text: 100% (moved as is)").

Real examples:
- `exemple_journal_D14_v1.md`: one entry;
- `exemple_journal_complet_pilote_v4.md`: a complete log of 86 operations (anonymized version; v3, which contained names, has been withdrawn).

Both are in `Revision\00_competences_claude\skills_ressources_par_skill\journal-modifications-d14\` on the PC, and in `/home/claude/00_competences_claude/skills_ressources_par_skill/journal-modifications-d14/` in the cloud.

## 2. Record each operation at planning time

Describe each operation with a record. The simplest way is a Python module `OPS = [dict(...)]`, applied as is by the revision engine:

| Field | Content |
|---|---|
| `id` | M-001 (modification), D-01 (move), F-01 (formatting); agent prefix if there are several agents (A2-M001) |
| `type` | `remplacer` (pairs old → new), `supprimer_par`, `supprimer_bloc`, `deplacer` (`de`, `vers`, `ou`), `inserer_avant` / `inserer_apres`, `remplir`, `format_par` |
| `mandat` | list: threads (F49), meeting segments (T26), decisions (D7), "message item 2" |
| `justif` | `commentaire` (comment), `restructuration` (restructuring), `redondance` (redundancy), `residu` (residue), `renvoi` (cross-reference) |
| `probleme`, `solution`, `pourquoi` | complete sentences, quotations in double quotes |
| `info` | the additional information, if there is any |
| `garde` | for a redundancy: (paraId, exact quotation of the kept passage, location and other paraIds that carry it) |
| `revue_c5` | mandatory if the kept passage covers less than 80% of the deleted words |

Also add `REPONSES = {fil: « Fait : … (M-001). »}`, one short reply per reviewer thread.

Why a structured record: the same fields feed the application of tracked changes, the automatic checks and the log. There is thus never a gap between what is done and what is written.

## 3. Checks to attach to the log

The log reproduces the table of checks of the revised document, because it proves that text preservation was upheld:

| Check | What is verified |
|---|---|
| C1 | Identical cover, byte for byte (if it is excluded from the revision) |
| C2 | Each operation is justified; in a section without comments, only restructuring, redundancy, cross-reference or residue; for a redundancy, the kept passage is quoted and found in the accepted version |
| C3 | Words inserted outside moves ≤ 2% of the body |
| C4 | Text "moved to" identical to text "moved from" |
| C5 | Numbers, identifiers or codes and references [n] that were deleted remain present elsewhere; content words covered at 80% or more, otherwise a manual review is recorded |
| C6 | One complete entry per operation |
| C7 | Comments kept, plus the replies; XSD validation; rejecting all of the author's revisions gives back the base (`validate.py --original base --author "<auteur>"` of the docx skill, and `docx_couches` v3, tracked formatting included); no stale cross-reference in the body |
| C8 | Formatting of the accepted view: `controler_mise_en_forme comparer <base> <révisé> --auteur "<auteur>"` with no new gap; headings kept after a real acceptance |

The reference verifier is `verifier_pilote_v8_v2.py`, in the project's `scripts` folder.

## 4. Generating the log

The scripts are in `skills_ressources_par_skill/journal-modifications-d14/scripts/` of the competence workspace (on the PC: `Revision\00_competences_claude\skills_ressources_par_skill\journal-modifications-d14\scripts\`); if they are not in the cloud, fetch them with `device_stage_files`.

1. `journal_D14_pilote_v4.py <module_plan> <journal_technique.json> <controles.md> <base.docx> <carte_paragraphes.jsonl> <carte_sections.json> <classement_segments.json> <sortie.md> [pages_suivi pages_lecture pages_base]`
   - The technical log comes from the application: for each operation, before/after, mapping source → moved copy, keys of the inserted paragraphs.
   - For another project, adapt:
     - the scope of threads and segments (`list(SECT)[2:17]`);
     - the decision labels (`DEC`);
     - the names of the categories (`NOMS`);
     - the particular locations (`LIEU`).
2. **The Word log reuses the formatting of the report it accompanies**: font, sizes of the body, headings, cells and captions, bullets, table headers, footer, typographic apostrophes. This format is read **in the report itself**, never from memory.
   - `md_vers_docx_v3.js` writes in Calibri 9.5 pt with blue headings: it is not suitable for a log that accompanies the report. (History, 16 Oct. 2026: the logs were delivered in this format because this skill prescribed this script.)
   - Builder in the report's format: project script `17_comparaison_v6.0.4/90_scripts/construire_docx_format_rapport_v5.py`, to be promoted into `outils/` by the pilot of the three tool levels. First search the catalogue to see whether it has been promoted (`python3 outils/chercher_outil.py docx format rapport`).
3. **Check before delivering**:
   - validation of the docx (`validate.py` of the docx skill);
   - **formatting profile identical to the report's**: `python3 outils/controler_mise_en_forme.py releve <rapport.docx>` then `… releve <journal.docx>`; the document font and the body size must be the same (example from report v6.0.10: Times New Roman, 22 half-points, i.e. 11 pt; the log delivered with it was in Calibri, 19 half-points);
   - PDF render with LibreOffice; look at 2 or 3 pages (summary, an entry, a table) **next to a page of the report**, comparing headings, bullets, tables and captions.

Structure of the log produced:
1. Summary (number of operations by type and by justification, moved paragraphs, share of inserted words, replies, pages) and table of checks;
2. Entries, grouped by category of the plan, in order of application;
3. Comment threads in scope: author, excerpt, operations, reply;
4. Meeting segments: status (addressed by…, already done by the author, acceptable, author point, deferred);
5. Points for the author (images, questions, cover cross-references, renumbering);
6. Technical note (display of moves, LibreOffice limitations).

### Formatting pass (F-… operations)

A formatting pass (for example `harmoniser_mise_en_forme`) produces hundreds of similar operations. The log keeps one entry per operation, in a compact form:
- one category per rule (H1 sizes, H4 blank lines left by a deletion, H5 empty paragraphs, H7 residual fragments, H8 merges on acceptance…);
- at the head of the category, once: **`Problème`** ("Problem"), **`Information additionnelle`** ("Additional information") (none), **`Solution et pourquoi`** ("Solution and why"), `Texte d'origine` (100%, no word changed);
- then a table, one row per operation: `F-<règle>-NNN`, section, ¶ (paraId), original revision of the defect (anonymized author), excerpt, before → after;
- any deletion of text (residual fragment) keeps a complete entry, with **`Passage supprimé`** ("Deleted passage") and **`Revue C5`** ("C5 review").

Reference generator: `scripts/journal_D14_mise_en_forme_v2.py <source.docx> <révisé.docx> <journal_technique.json> <dossier_controles> <sortie.md>`, then the report-format builder and the checks of § 4 (steps 2 and 3).

## 5. Pitfalls already met (and their fix)

- **Badly cut deleted passage**: a character-by-character diff gives "’exemple … L". Derive the passage from the (old, new) pairs by removing the common prefix and suffix.
- **Operation on a moved paragraph**: state the destination section, with `(paragraphe déplacé depuis « … »)` (in English: paragraph moved from "…"). Otherwise the reader looks in the wrong place. A move to a copy that has already been moved (`vers = D:…`) is resolved recursively.
- **Residues** (punctuation left by an accepted deletion): the neighbouring thread is not their mandate. Wording: `Mandat ou fil au même endroit` ("Mandate or thread at the same place").
- **Numbering**: state that the section numbers are those of the base (before renumbering).
- **A pure deletion is shown only once** (`Passage supprimé`), not also as `Modification → (supprimé)` ("Change → (deleted)").
- **Internal cross-references** ("see M-061", "D-04"): check that each identifier cited exists and designates the right operation. Fix them in a new version of the plan, never in place.
- **Table of checks**: take only the first table of the checks file, not the C5 coverage table.
- **Docx**: without a minimum width, short columns ("F223", `conforme` (compliant)) break letter by letter.
- **Names of people**: the examples and resources of this skill contain none; the authors of revisions are designated there by their role (User, Colleague A…), via `anonymiser`.
- **Log format**: a generic builder imposes its own font and colours. The log of a report takes the report's format, verified by the formatting readout (font and body size) and by pages looked at side by side (§ 4).
- **Location of an operation**: the last visible heading before the paragraph can mislead (moved section, part without a heading style); for a fragment or an orphan line, add `juste avant « <titre suivant> »` ("just before "<next heading>"").

## 6. Versions and backup

- Never overwrite: plan v2, v3…, journal_v1.md, v2…, docx v3.1. Drafts stay, marked as superseded in a LISEZMOI file.
- After each log produced: check that the relay has sent it (compliant receipt; `sync-cloud-pc` skill).
- The tools in `00_competences_claude/outils/` are called by their shortcut (`python3 outils/<outil>.py`), never by a versioned file.
- Claude's comments in reports and in replies to threads: short (`Fait : …` ("Done: …"), `Question : …`, `Mineur : laissé à l'auteur` ("Minor: left to the author")).
