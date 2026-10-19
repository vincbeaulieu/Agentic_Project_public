---
name: "application-corrections-rapport"
description: "Apply to a Word report the corrections from a critical review or from a reviewer, as tracked changes, with a reply in each comment thread, questions for the author and checks."
---

# Applying corrections to a Word report

## Objective

Produce a new version of the report in which:
- **every change is a revision mark** that the author can accept or reject;
- **every comment thread receives a reply with a status**.

The author must be able to:
- quickly check what was done;
- reject everything and get back the document received;
- see at a glance what is waiting for their decision.

This skill follows `revue-critique-rapport`, but it works with any Word comments, including free remarks from a human reviewer.

## Vocabulary

- **The author**: the person who decides the content of the report.
- **The commenter**: the author of a comment.
- **The received document**: the commented .docx that was supplied. It is the reference for the "reject all" view. An original without comments, if there is one, is for information only.

## Inputs

**Minimum required:** the commented report (.docx).

**Strongly useful:**
- the review report (.md): prioritised plan, contradictions between references;
- the reference reports;
- the register of facts;
- a prompt or correction instructions.

If instructions are supplied, their rules and decisions take precedence over this skill. Copy them into `journal.md`.

## Proportioning the effort

**Fewer than ~60 comments:**
- do the triage and the plan yourself, in a single `plan_bloc_1.json`;
- folders 02 to 04 can be merged;
- keep an independent verifier in C5.

**More than ~60 comments:**
- one sub-agent per block, split at chapter boundaries. Reuse the review's split if there is one; otherwise plan about 50 comments per block.

**More than ~30 questions for the author:**
- group them by theme;
- put the critical and major decisions first;
- offer "★ recommendation for everything else".

## Reply statuses

| Code | Label in the thread | When |
|---|---|---|
| TRAITE | `Traité` ("Addressed") | The request is applied in full, at every location. |
| PARTIEL | `Partiellement traité` ("Partially addressed") | Part of it is applied. Say which part and what is pending (Dx/Fx). |
| EN_ATTENTE | `En attente de décision` ("Awaiting decision") | Depends on an open decision or piece of information (Dx/Fx/CR-xx), or on a passage "to be redone". |
| NON_TRAITE | `Non traité` ("Not addressed") | Well-founded request that cannot be applied here (source data missing, recalculation required, contrary decision by the author). Give the reason. |
| SANS_OBJET | `Sans objet` ("Not applicable") | Already handled, a mere remark or approval, a question answered without changing the text, a wrong reading that has been verified. |

## Rules and reasons

1. **Never overwrite.**
   - The deliverable is a new file, named according to the strict format (`<Nom>_v<version>.docx` for a deliverable, `<Nom>_vX.Y.Nc.docx` for a working revision) and placed by `outils/livrer.py`, which refuses any existing name and any version outside the convention (see C6).
   - Non-overwriting is proved by the successive checksum manifests (rule E5 of `evaluer_travail`).
   - Working files are versioned (`plan_final_v1`, `v2`…).
   - Sources are read-only (`chmod a-w`), and their SHA-256 checksums are verified at every phase.
2. **Everything is tracked under a distinct author**, for example `Correction - Claude`, initials CC. This covers text, inserted or deleted paragraphs, and equations.
   - **Proof:** rejecting only our revisions gives back the received document.
   - **Pre-existing revisions by other authors (lesson LC-010):**
     - **Reviewers** (reviewing colleagues, guests): their revisions are **suggestions**. Never accept them in bulk and never use them as a working base: they stay tracked in the deliverable.
     - Each one receives a verdict after the check of rule 11: retained, retained with adjustment, not retained (original text restored by our insertion) or author's decision.
     - **Author**: the author's revisions are authoritative.
     - **Technical:** never modify the inside of another author's revision. Use the multi-author engine `00_competences_claude/outils/moteur_revision_multi.py`, through `outils/appliquer_suivi.py`:
       - our deletion nests inside their insertion;
       - our insertion is placed next to it, in a split container.
     - Check L3 of `outils/evaluer_travail.py` verifies that their revisions are still there.
3. **Do not touch the results.**
   - A value, unit or date changes only if two conditions are met: a comment points out a transcription error, **and** a reference confirms it (same value, same unit, same rounding). Then cite the reference in the justification.
   - **Without a reference:** the change goes to B and is made only after explicit confirmation by the author, cited in the form "confirmed by the author, Fx".
   - **Equations:** you may reformat them, never change their substance.
4. **Comments are kept.**
   - Never delete a comment and never modify its `done` attribute.
   - Read the whole thread: the author's last message sets the request.
   - **One reply per thread**, on the root comment. It starts with `[Correction vX.Y | <Libellé>]`.
   - Threads that are already resolved (`done="1"`) receive no reply unless told otherwise. They are noted SANS_OBJET in the journal.
5. **Invent nothing.** Information absent from the files remains a question: data, name, identifier, owner, URL, parameter… Choices that change the message (term, conclusion, structure) go back to the author.
6. **Open questions stay open.** Ask the author how to handle a question that remained unanswered:
   - (a) passage unchanged and comment EN_ATTENTE;
   - (b) ★ recommendation applied.

   Without instructions, apply (a). Insert a marker `[À COMPLÉTER : …]` ("[TO COMPLETE: …]") only if the author asks for it.
7. **A passage that the author declares "to be redone" is not rewritten**. All comments that depend on it go EN_ATTENTE, including those that reuse its results elsewhere, with a pointer to the decision.
8. **No change without a mandate.** Every modification carries at least one existing `comment_id` or a decision identifier (Dx). This also applies to cross-cutting additions and to equation reformatting.
9. **Keep a trace.**
   - Keep `journal.md` up to date after each phase.
   - If the session is linked to the user's computer, mirror the work folder into the user's folder after each phase, creating the folders first. That folder is the durable record of the work.
10. **Read the request, not only the editing gesture (lesson LC-008).**
    - **Replacement, not deletion.** A deletion accompanied by "it is not X that is needed here, but Y" is a **replacement of X by Y**. The text of the comment (the reviewer's last message) sets the request.
    - **Rephrase.** Rephrase each request in one sentence.
    - **Status `Traité`.** It is allowed only if Y appears in the report.
    - **Check.** Detector DR-07 (`outils/detecteurs_rapport.py`) flags replacement requests whose requested text is absent.
    - **Evidence.** Rev1, thread F310: §1.1 was deleted and the reply said `Traité`, whereas the guest had asked to write the objective of the report there.
11. **Check that each fix settles the point raised, before applying it (lesson LC-009).** This applies to every fix: the reviewer's, one from a previous pass, or our own.
    1. Write the **point raised word for word**, with its source (thread or transcript segment).
    2. Check that the fix **settles that point**, fully and correctly, at every location concerned.
    3. Check that it **creates no new problem**: unique information lost, reference [n] no longer cited, cross-reference to a section or table that has disappeared, error, contradiction, inconsistent term.
    4. Check that the **announced status is true**.

    Detectors DR-01 to DR-06, run before and after application, make points 3 and 4 automatic. When in doubt: author's decision.
12. **Check the accepted view, formatting included (lesson LC-019).** The reader will see the document after "Accept All": that is the view to check, not the tracked text.
    - **Typical defects of a pass**: inserted passage without properties (default 12 pt in an 11 pt body); emptied paragraph whose mark remains (empty line or bullet); emptied table whose grid remains; caption deleted from a table that is kept; fragment left outside the scope of a deletion ("xyz."); deleted mark that merges a paragraph into a heading (depending on the software, the heading becomes body text); Markdown emphasis in agent text ("*word*").
    - **Tools**: `outils/controler_mise_en_forme.py` (accepted view simulated the way Word does it; deviations MF1 to MF10, with the revision author who introduced them) and `outils/harmoniser_mise_en_forme.py` (corrections in tracked changes under a dedicated author; H9, which deletes an emptied table, only on decision).
    - **After each pass**: `controler_mise_en_forme comparer <avant> <après> --auteur "<auteur de la passe>"`. Exit code 1 (a new deviation by this author) blocks the pass.
13. **Defect reported in a deliverable: investigate, present, plan, test, present, apply after approval (lesson LC-020).**
    1. Investigate the cause and origin (revision author, version, mechanism) with a deterministic tool, on the version history if needed.
    2. Present the findings to the user: what they will see, where it comes from, how it happened.
    3. Plan the correction in a versioned plan (`01_plan/plan_correctif_vN.md`): rules, number of corrections, cases left to their decision.
    4. Test: unit tests with a **control** (without the fix, the test fails), a trial on the real document, a comparison with the target environment (real acceptance, PDF rendering).
    5. Present the plan and the test results; put the decisions to the user (AskUserQuestion).
    6. Apply only after approval, in a new work folder and a new version, the approval quoted word for word in `TRAVAIL` (`approbation_plan`).
    7. Update tools, lessons and skills (proposals, never approved by me).

## Work folder

The folder follows the **mandatory organisation** (skill `cadre-travail-deterministe`): `NN_sujet/` with `00_sources/`, steps `01_…` to `89_…`, `90_scripts/`, `95_journal/`, `98_livrables/` and `99_livrables_modifiables/`.
- **Creation**: with `00_competences_claude/outils/creer_travail.py`. It copies the sources as read-only with their checksums, and creates `TRAVAIL_v1.json` (source, revision author, target version, coverage, reviewers) and `LISEZMOI_v1.md`.
- **Steps**: the correspondence with phases C0 to C6 is shown below. The old names are kept in parentheses for reference:

```
NN_corrections_<sujet>/
  LISEZMOI_v1.md, TRAVAIL_v1.json
  00_sources/        docx reçu, original éventuel, références, rapport de revue, consignes ; sha256_sources_v1.txt (lecture seule)
  01_inventaire/     commentaires_tous_v1.json, suivi_commentaires_v1.md, detecteurs_<source>_v1.json (constats déterministes de départ)
  02_triage/         consignes_tri_v1.md, triage_bloc_<n>_v1.json, triage_consolide_v1.json
  03_decisions/      questionnaire_auteur_v1.md, decisions_auteur_v1.json
  04_plans_blocs/    consignes_plans_v1.md, plan_bloc_<n>_v1.json, plan_transversal_v1.json, resolution_conflits_vN.json
  05_application/    plan_final_vN.json, _essais/ (essais jetables, dossier exempté de version)
  06_verification/   consignes_verification_v1.md, texte_accepte/modifications/reponses_<v>.md, verification_independante_vN.json, controles_<v>.json
  90_scripts/        scripts propres au travail (les outils généraux restent dans 00_competences_claude/outils)
  95_journal/        journal_v1.md (consignes recopiées, phases), manifestes/, evaluations/
  98_livrables/      <Rapport>_v<version>.docx, Journal_corrections_v<version>.md, empreintes (lecture seule, posés par outils/livrer.py)
  99_livrables_modifiables/  copies modifiables des mêmes fichiers
```

Create one task per phase (C0 to C6) and tick it off as you go.

## C0 — Preparation

1. Copy the sources and compute their SHA-256 checksums. If the user's folder is linked, verify that the copy is identical to their file.
2. **Paragraph index** (`_paragraphes.jsonl`): part (document, footnotes, endnotes, headerN, footerN), index, `w14:paraId`, style and exact text, tabs included. Ignore `mc:Fallback`.
   - If the review's index exists, reuse it after checking that the paraIds match.
   - If the document has no paraId, identify paragraphs by part and index.
3. **Pre-existing revisions**: count them by author and by type (`ins`, `del`, `moveFrom`/`To`, `rPrChange`, `pPrChange`), then apply rule 2.
4. **Starting deterministic findings.** Run `00_competences_claude/outils/detecteurs_rapport.py <docx reçu> --json 01_inventaire/detecteurs_<source>_v1.json --md …`. These findings are the baseline for the "new problems" check of C4.
5. **Starting formatting.** Run `00_competences_claude/outils/controler_mise_en_forme.py releve <docx reçu> --json 01_inventaire/mise_en_forme_<source>_v1.json`. Deviations already present (with their origin) are reported to the author and are not attributed to the pass.

## C1 — Comment inventory

1. Fill in `commentaires_tous.json`: id, author, initials, date, parent, resolved, anchored text, part, paragraph, section, approximate page, block, content.
2. **Comment in review format** (`[Catégorie | Gravité | id_constat]` / `Constat` ("Finding") / `Référence` ("Reference") / `Correctif proposé` ("Proposed fix") / `Autres emplacements concernés` ("Other affected locations")):
   - split out its fields; the `id_constat` is optional;
   - resolve the "other locations" into a list `paragraphes_concernes`: a merged comment applies everywhere;
   - exclude the `[Note de lecture]` ("Reading note") (SANS_OBJET).
3. **Free comment**: write three fields.
   - `demande`: what is requested, in one sentence (rule 10: "replace X by Y" when the comment says "not X but Y", even if the reviewer only deleted X).
   - `nature`: `correction`, `question`, `remarque` ("remark") or `approbation` ("approval").
   - `portee`: `locale` ("local"), or `partout` ("everywhere"). For `partout`, find all occurrences with Grep and fill in `paragraphes_concernes`.

   If a request can be read in two ways, classify it as B.
4. Produce `suivi_commentaires_v1.md`, a readable table.

## C2 — Triage and questions for the author

1. **Triage.** Do it yourself or through sub-agents (with `consignes_tri.md`), one result per comment or per thread.
   - **A — directly applicable:** typo, cross-reference, caption, specified rephrasing, detail present in a reference, terminology already decided, requested formatting.
   - **B — decision or information from the author needed:** several options, contradiction between references, missing information, change of a conclusion or of the message, value to change without a reference, ambiguous request, question put to the author.
   - **C — not applicable:** source data unavailable (workbook, image), recalculation required, already handled, wrong reading (to be checked in the text), purely informative remark.

   For each comment, give: paragraphs to modify, effort (S/M/L) and the check done in the text. For B, add: question, options, recommended option ★, dependencies, missing information.
2. **Consolidation** in `triage_consolide_v1.json`.
3. **Questionnaire** `questionnaire_auteur_v1.md`, with **all the questions at once**:
   - **Header:** A/B/C count, how to answer ("OK for everything except Dx"), decisions already made, and the question of how to treat unanswered items (rule 6).
   - **Part I:** decisions D1…Dn, each with its subject, the comments concerned, a ★ recommendation and the other option.
   - **Part II:** information items F1…Fn, with what will be done if there is no answer.
   - **Part III:** comments not applied (C), with the reason.
4. **Sending and waiting.** Send the questionnaire and **wait for the answers** before C3, because they condition the plans.
   - If the user says to continue, or if the author cannot be reached: apply the A items, put the B items in EN_ATTENTE (option a) and deliver the questionnaire with the docx.
   - If an answer is ambiguous or addresses something other than the question, rephrase it and have it reconfirmed.
5. **Recording** in `decisions_auteur_v1.json`: what the author said, word for word; its consequences for the statuses; a key `ouvertes` that explicitly lists the questions left open; a key `sans_reponse` (option a or b).

## C3 — Correction plans

Each sub-agent (or you) writes **only** a `plan_bloc_<n>.json`. Nobody touches the docx: a single engine applies everything, which guarantees uniform revision marks. Write the cross-cutting additions decided by the author in `plan_transversal_v1.json`.

**Plan format:**

```json
{"edits": [
  {"edit_id": "B3-001", "comment_ids": ["245"], "decision": null, "type": "remplacer",
   "partie": "document", "paragraphe_index": 812,
   "ancien": "<sous-chaîne EXACTE et unique du texte courant (vue « tout accepté ») du paragraphe, la plus courte possible>",
   "nouveau": "<remplacement>", "justification": "<1 phrase ; cite la référence ou la décision si une valeur change>"},
  {"edit_id": "...", "type": "inserer_paragraphe_apres", "paragraphe_index": 559, "modele_paragraphe": 559,
   "texte": "...", "apres_edit": "<edit_id d'un paragraphe déjà inséré, facultatif>"},
  {"edit_id": "...", "type": "inserer_paragraphe_avant", "paragraphe_index": 17, "modele_paragraphe": 139, "rpr_de": 16, "texte": "..."},
  {"edit_id": "...", "type": "supprimer_paragraphe", "paragraphe_index": 900},
  {"edit_id": "...", "type": "equation", "remplace_paragraphes": [522, 523],
   "lignes": [{"latex": "<formule LaTeX, sans $>", "numero": "(<numéro>)"}]}
 ],
 "reponses": [{"comment_id": "245", "statut": "TRAITE|PARTIEL|EN_ATTENTE|NON_TRAITE|SANS_OBJET",
   "texte": "Traité : … | Partiellement traité : … (reste : Dx) | En attente de décision (Dx) : … | Non traité : <raison> | Sans objet : …",
   "edit_ids": ["B3-001"]}]}
```

**Verification of each fix (rule 11), mandatory in the plan.** Each reply also carries:
- `point`: the point raised, word for word, with its source;
- `regle_le_point`: `oui` ("yes"), `non` ("no") or `partiel` ("partial");
- `nouveau_probleme`: `aucun` ("none") or the description;
- `statut_vrai`;
- for a reviewer's revision: `verdict` (`retenue` ("retained"), `ajustée` ("adjusted"), `non retenue` ("not retained") or author's decision).

**Rules to copy into `consignes_plans.md`:**
- The author's decisions are authoritative. Rules 3, 5, 7 and 8.
- Modify the smallest portion of text that settles the problem, in the style of the report. Typography is that of its language (in French: a space before `:`, `;`, `?` and `!`, guillemets `« »`, decimal comma).
- Apply the correction to **all** the `paragraphes_concernes`, even outside the block.
- A table cell is a paragraph. Adding or deleting a table row goes to B, unless the engine knows how to do it.
- Never modify the displayed text of a field (REF, SEQ, PAGE, TOC): it would be overwritten on update. Fix the target (caption, bookmark).
- Several "replace" edits on the same paragraph are applied in order: the second `ancien` must exist after the first replacement.
- If you renumber an equation or a table, update the cross-references.
- **Statuses:** A gives TRAITE, except for an open decision or a passage "to be redone" (EN_ATTENTE). B gives TRAITE or PARTIEL only if the decision settles it. C gives NON_TRAITE or SANS_OBJET, with the reason. When in doubt: EN_ATTENTE.

**Check before handing in a plan** (script `check_plan.py`, to be written or adapted):
- each `ancien` exists exactly once in the current text, simulating the successive replacements;
- the indexes are valid;
- no `ancien` overlaps a field, a bookmark or another author's revision;
- each LaTeX converts to OMML with pandoc.

Expected result: "0 errors".

**Presentation of equations.** Touch them only if a comment or the author asks, following the convention the author sets. If none is set, propose this one in the questionnaire:
- one equation per line, as an Equation object (OMML), with real subscripts, superscripts, stacked fractions and radicals;
- the equation centred, its number on the right; one line per number, with sub-numbers a, b, c if needed;
- the title built into the introductory sentence;
- a legend introduced by "where:", one symbol per line;
- in an appendix, a numbering (A.1) that cannot be confused with that of the tables.

## C4 — Merge, application, automatic checks

1. **Merge** (`merge_plans.py`): concatenates the plans, simulates the text of each paragraph and lists the overlaps and conflicts. Resolve them in `resolution_conflits_vN.json`:
   - `drop`: removes a duplicate;
   - `patch`: rebases `ancien` or `nouveau`;
   - `patch_post`: corrects after a global harmonisation. A global harmonisation (for example an acronym replaced everywhere) produces artefacts such as "X (X)" or a wrong article; re-read it.

   **A patch is merged with the existing fields; it does not replace the dictionary.** A patch that kept only `nouveau` would lose its `ancien`, and the conflict would come back.

   Repeat until **0 conflicts**. The simulated text (`_texte_simule_vN.json`) is what the "accept all" view is expected to show.
2. **Application**: `apply_corrections.py <docx reçu> <plan> <sortie> <journal>` (see the recipe). Do trial runs `_essai_N.docx` first.
3. **Checks** (`verify_tracked.py`, results in `controles_<v>.json`). The first check proves that everything is tracked:
   - (a) `validate.py` from the docx skill with `--original <docx reçu> --author "<auteur>"`. It compares text only;
   - (b) programmatic rejection of **only our** revisions, then normalised XML comparison of each part with the received document. Adjacent runs with the same rPr are merged, and rsid, paraId and comment markers are ignored. No deviation is tolerated, and that includes `m:oMath` and `m:t`;
   - (c) third-party check with `pandoc --track-changes=reject` then `=accept`: diff with the received document and with the simulated text.

   - (d) `00_competences_claude/outils/evaluer_travail.py <dossier>`: organisation, checksums and non-overwriting, naming and versions, Claude comments (K1, K2), Word deliverable (D1 to D5) and reviewers' revisions kept (L3). The verdict `CONFORME` ("COMPLIANT") is required;
   - (e) **new problems**: run `outils/detecteurs_rapport.py` again on the output and compare with the starting findings (C0).
     - Any new orphan reference (DR-01) or new broken cross-reference (DR-02) is **blocking**.
     - Any new typographical error (DR-04) or inconsistent list (DR-05) must be corrected.
     - Every sentence we delete (DR-03) is justified in the plan.
   - (f) **formatting** (rule 12): `outils/controler_mise_en_forme.py comparer <docx reçu> <sortie> --auteur "<auteur>"`. A new deviation by our author is **blocking** (heading turned into body text, empty line, size, fragment, emptied table, Markdown);
   - (g) **real acceptance**: a copy accepted by LibreOffice (`accept_changes.py` from the docx skill) is compared with the simulated accepted view (paragraph texts and styles: every heading stays a heading). Known LibreOffice limitations, with no effect in Word: a deletion nested in an insertion is kept, a deleted row stays empty, a section paragraph is removed;
   - (h) the rejection of our revisions (`docx_couches` v3, check D3 of `evaluer_travail` v8) also covers our tracked formatting changes (`w:rPrChange`, `w:pPrChange`).

   Content checks follow:
   - the "accept all" view equals the simulated text, paragraph by paragraph, with no deviation at all;
   - original comments and revisions intact;
   - reply markers complete;
   - only one new revision author;
   - no orphan modification: every edit has an existing `comment_id` or a Dx;
   - every unresolved root thread has exactly one reply: none missing, no duplicate;
   - **diff of the numbers** (with their units) between the reject view and the accept view: every changed number corresponds to an edit whose justification cites a reference or a decision;
   - proper names, acronyms and numbers in a `nouveau` that are absent from the `ancien`, the comment, the references and the decisions are listed, then justified or removed;
   - equations: the LaTeX read back by pandoc from the old and the new version contains the same symbols, operators, subscripts and superscripts. Any deviation is justified. If LibreOffice does not display the OMML (common in a container), say so and ask for a visual check in Word.

## C5 — Independent verification

1. Prepare `texte_accepte_<v>.md`, `modifications_<v>.md` (before/after, with comment and justification) and `reponses_<v>.md`.
2. Hand them to 1 or 2 fresh sub-agents, with `consignes_verification.md`. They verify:
   - that each correction does what was requested, at every location;
   - that no value changed without a source;
   - that no open decision was applied;
   - that the statuses are true;
   - that no new inconsistency appears (a value corrected here but not in the Summary);
   - language, typography, cross-references and numbers.

   They produce `verification_independante_N.json`: id, severity, finding, proposed correction.
3. Integrate the well-founded findings into `resolution_conflits_v(N+1).json`, then redo C4 until all the checks are green.

## C6 — Final version and journal

1. Apply the final plan, then hand over the deliverables with `00_competences_claude/outils/livrer.py <dossier> <fichier>:<Nom>[:<variante>] …`.
   - The tool names the files `<Nom>_v<version>[_variante]`, where the version is the `version_cible` of `TRAVAIL`. It must equal the expected version:
     - the user's rule or decision specific to the document, recorded in `TRAVAIL` (`decision_version`). For the report: source v6.0.4-rev1 → deliverable v6.0.5-rev1;
     - otherwise, the general convention v(X+1).0.0, X being the initial version of the source.
   - Never a "next free major". The tool refuses a version outside the convention; `evaluer_travail` (N3) checks it too.
   - It makes them read-only in `98_livrables`, with their checksums, and copies them into `99_livrables_modifiables`.
   - It then runs `evaluer_travail`.

   Rerun all the C4 checks, re-verify the SHA-256 checksums and render the cover page and the modified pages to PDF.

   **Acceptance test in the target environment (lesson LC-018).** Word is the author's tool; LibreOffice is only a test bench. The delivery message gives a short test procedure (copy, Review > Accept All Changes, Navigation Pane, two or three precise places) and does not present the document as verified in Word until that procedure has been carried out.
2. Write `Journal_corrections_v1.md`, in 7 sections:
   1. **Overview**: comments kept, replies by status, operations by type, revision marks, equation lines.
   2. **Checks** and results, limits included.
   3. **Author's decisions applied.**
   4. **Points of attention**:
      - update the table of contents and the fields in Word (F9);
      - regenerate any table-of-contents line added by hand;
      - passages "to be redone";
      - data to correct at the source;
      - version and date on the cover page, left unchanged if nobody asked for a change.
   5. **Questions still open**: a Dx/Fx/CR-xx table with the comments concerned.
   6. **Tracking by comment**: id, author, location, category and severity, status, number of modifications, reply published.
   7. **Working files.**
3. Send the docx and the journal. The final message takes 3 or 4 lines: statuses, checks, limits, actions for the author.

## Technical recipe — application engine (lxml)

**Visible text**
- Take only the runs whose owner paragraph is the right one, outside `w:del` and outside `m:oMath`.
- `w:tab` counts as `\t`, `w:br` counts as `\n`.
- Distinguish a field's result from its code (`instrText`).
- Process each part (document, notes, headers, footers) separately.
- Text box (`mc:Choice`/`mc:Fallback`): apply the modification to `mc:Choice` and delete the matching `mc:Fallback`, or apply it to both.

**Replace**
1. Find `ancien` after normalisation (non-breaking spaces, apostrophes).
2. **Reduce to the words that change**: remove the common prefix and suffix, snapping to word boundaries.
3. Cut the runs at the boundaries.
4. Wrap the deleted runs in `w:del`, renaming `w:t` to `w:delText`.
5. Insert a `w:ins`:
   - if the replaced zone has only one rPr, keep it;
   - if it mixes several, take the rPr of each kept segment and flag the edit for review. Otherwise a whole sentence may turn bold, or a superscript such as "m²" may be lost;
   - for a pure insertion, take the rPr of the preceding run;
   - never an inserted run without rPr: at minimum the paragraph's dominant size (`sz`, `szCs`), otherwise it takes the document's default size (rule 12);
   - in all cases, remove from the copied rPr the comment-reference `rStyle`, `rPrChange`, `w:ins` and `w:del`;
   - an agent's text is cleaned of any Markdown syntax (`*…*`, `**…**`, `#`, `` ` ``) before being inserted.
6. If the run to delete is one of our own `w:ins`, remove it directly.
7. **Never place in a `w:del`**: `commentRangeStart`/`End`, `commentReference`, `bookmarkStart`/`End`, or part of a field. Leave these elements in place, outside the deleted runs.

**Insert a paragraph**
- Copy the template's `pPr`, without `sectPr`, without `pPrChange` and without an inherited mark.
- Add `<w:rPr><w:ins …/></w:rPr>` in the `pPr` (inserted paragraph mark), a `w:ins` run and a new `w14:paraId`.
- Respect the order of successive insertions and `apres_edit`.

**Delete a paragraph**
- Put all its runs in `w:del` and add `<w:del …/>` in `pPr/rPr`.
- Never mark as deleted the mark of a paragraph that carries a `sectPr`, nor that of the last paragraph of a cell or of the body. Empty its runs, and mark the previous paragraph's mark instead.
- **Emptying a paragraph means deleting it**: text in `w:del` **and** mark in `w:del`; otherwise an empty line remains after acceptance.
- **Merge on acceptance**: if the deleted paragraph and the paragraph that follows it do not have the same properties (style, indent, spacing), give it, as a tracked change (`w:pPrChange`), those of the paragraph that remains. Otherwise the result depends on the software, and a heading can become body text.
- **Emptying a table means deleting its rows** (`w:trPr/w:del`, text and cell marks in `w:del`); deleting a caption without the table, or the reverse, goes to B.
- **Boundaries of a deletion**: on word boundaries, checked afterwards (no fragment of 8 characters or fewer survives alone from an almost entirely deleted paragraph).

**Revisions**
- `w:id` unique among all the `w:id` of the package, and greater than the maximum.
- `w:date` in the format `AAAA-MM-JJThh:mm:ssZ`, identical for a whole pass.

**Equations**
1. Convert the LaTeX to OMML with pandoc (`$…$` in a .md, then extraction of `m:oMath`).
2. Put back in schema order the children of `m:dPr` (begChr, sepChr, endChr, grow, shp, ctrlPr), of `m:mcPr` (count, mcJc) and of `m:mPr`.
3. Remove `m:sty` when `m:nor` is present.
4. Wrap the **entire content** of `m:oMath` (including `m:f`, `m:rad`, `m:d`…) in a `w:ins` placed inside `m:oMath`. The type `CT_RunTrackChange` admits mathematical elements. For an existing equation that is deleted, do the same with `w:del`.
5. Final line: centred tab, equation, right tab, number. Define the tab stops in `w:tabs`, with the centre at half the text width. The tab and the number go in separate `w:ins` elements.
6. The number takes the rPr of an existing number (pattern `\(([A-Z]\.)?\d+[a-z]?\)`) or a neutral rPr, never the italic of Cambria Math.

**Replies**
- Follow the comment recipe of the `revue-critique-rapport` skill: comments, commentsExtended with `paraIdParent` equal to the last paraId of the **root** comment, commentsIds, commentsExtensible, people, and creation of the parts if needed.
- Place the markers next to those of the comment being answered.
- Make the first line bold: `[Correction vX.Y | Libellé]`.

**Package**
- Rewrite the zip keeping the order and attributes of the entries.

**Reference scripts**
- **Up-to-date general tools**: see `00_competences_claude/catalogue_outils/catalogue_outils_vN.md`, without rereading each tool. It lists `appliquer_suivi`, `moteur_revision_multi`, `docx_couches` (rejection of one author, tracked formatting included, comparable layers), `detecteurs_rapport`, `controler_mise_en_forme`, `harmoniser_mise_en_forme`, `evaluer_travail`, `creer_travail` and `livrer`. They are versioned and evaluated on a test bench.
- A previous mission may have left scripts in `travail_corrections/scripts/` (apply_corrections, check_plan, merge_plans, build_final_plan, verify_tracked, dump_review, c6_journal).
- If they are accessible, adapt them rather than rewriting everything. Their paths are hard-coded, and they only process `document.xml`.
