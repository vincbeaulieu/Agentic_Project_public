---
name: "redaction-rapport-sous-rapports"
description: "Write a final or summary report (.docx) from authoritative sub-reports: fact register, arbitrated contradictions, validated outline, traceability and concordance of every figure."
---

# Writing a report from reference sub-reports

## Goal

Produce a new report, clear for its audience, in which **every fact comes from an identified source** and is neither recalculated nor invented. The author also receives:
- the list of contradictions between sources that they arbitrated;
- the list of those that remain open.

The rigor is that of a critical review, applied to writing: a fact register, proof for each figure, an independent reread and versions with no overwriting.

## Inputs

- **Minimum required:** at least one reference report (.docx, .pdf or .md). These sub-reports are authoritative.
- **The rest is asked at scoping (R2)**: template, audience, desired outline, house conventions, new information that appears in no source.

## Scaling the effort

| Volume | How to work |
|---|---|
| Sources under ~40 pages in total and a report under ~20 pages | R1 and R4 done by yourself, without sub-agents |
| Larger volume | One sub-agent per source (R1), then one per block of 10 to 15 pages (R4), in parallel |

In every case, keep the independent verification of R6. Without a sub-agent tool, work in sequence and note it in the log.

## Rules and reasons

1. **The sources are authoritative. Nothing is invented.**
   - Each figure, decision, threshold, headcount or conclusion comes from the register (fact identifier) or from information given by the author (`AUT-nnn`).
   - Missing information becomes a question, never a plausible value.
   - Without a source, no causal link ("thanks to"), no judgment ("sharp increase", "satisfactory"), no trend and no comparison between sources. A transition sentence carries no fact.
2. **Do not recalculate.** Results are taken as they are: same value, same unit, same rounding.
   - A figure absent from the sources is a **calculated fact** `CALC-nnn` (total, average, variation, unit conversion). The register gives its formula, the IDs used, the script (`scripts/calculs.py`), the exact value and the rounding chosen. The author must approve it (decision Dx), and the report states that it is calculated.
   - Before any calculation, check that no source already gives this figure (annual cumulative total, restated figure). If one does, the source prevails.
   - Warning: the sum of the rounded values is not the rounded value of the sum.
3. **Contradiction between sources (`CR-xx`): do not decide.** Propose a wording and a ★ source, with the reason (more specialized, more recent). The author arbitrates before the writing.
   - A figure restated in a more recent source is not a contradiction. It is a revision `REV-xx`: the most recent value prevails, and the revision is flagged.
4. **Does the new report replace the sub-reports?** There is no default answer: ask the question.
   - **Yes**: replaced documents may become inaccessible. Ask the author how to mention them: citations in the text, a "Revision history and replaced documents" block on the cover page, or a traceability note. Apply their choice everywhere, reused figures included. The detailed traceability stays in the matrix, delivered separately.
   - **No**: the tags become references to the sources (for example "(Report X, § 3.2, p. 14)") or [n] calls to the bibliography, at the author's choice.
5. **Never overwrite.**
   - The deliverable is named `<nom>_v1.docx`, then v2, and so on. The working files are also versioned.
   - The sources are read-only (`chmod a-w`). Their SHA-256 sums are checked at the end of each phase.
6. **The reader first.**
   - A Summary without jargon, which says what needs to be decided.
   - A constant template for each chapter.
   - Acronyms defined at their first occurrence, and a glossary.
   - Verified cross-references.
7. **Draft sources.** Note for each source its date, version, status (draft or final), period and scope. A draft source is used only with the author's agreement. A change of scope between two periods is a limitation, to be mentioned in the report.
8. **Keep a trace.**
   - Keep `journal.md` up to date after each phase.
   - If the session is linked to the user's computer, mirror the work folder into their folder after each phase, creating the folders first. That folder serves as a durable trace of the work.

## Work folder

Create the folder `travail_redaction/` in the same parent folder as the sources:

```
travail_redaction/
  00_sources/        copies (lecture seule) + sha256_sources.txt
  01_inventaire/     <ref>_paragraphes.jsonl, _texte.md, _structure.md, _pagemap.json, figures/, graphiques/
  02_registre/       registre_<ref>.jsonl (+ vue .md), tables/<ID>.csv, calculs.jsonl, _entete_consolide.md
  03_cadrage/        questionnaire_auteur_v1.md, decisions_auteur_v1.json, plan_detaille_vN.md, conventions.md, glossaire_v1.md
  04_redaction/      consignes_redaction.md, section_<k>.md (balisé), synthese.md, conclusion.md, questions_ouvertes.jsonl
  05_assemblage/     contenu_balise_vN.md, build.(py|js), _essai_N.docx
  06_verification/   concordance_vN.json, couverture_vN.md, verification_independante_N.json, integrite_vN.md
  07_livrables/      <nom>_v1.docx, Matrice_tracabilite_v1.(md|xlsx), Journal_redaction_v1.md
  scripts/
  journal.md
```

Create one task per phase, from R0 to R7, and tick it as you go.

## R0 — Source inventory

Apply phase 0 of the skill `revue-critique-rapport` to each source:
- **.docx**: indexed paragraphs (`_paragraphes.jsonl`), tagged text `[§index p.page]`, structure, notes and headers, page map.
- **.pdf**: read the skill `pdf-reading`. Extract the text page by page, with the marker `[p.N l.k]`. Extract the tables with pdfplumber and check them against the page image. OCR the scanned pages: a figure obtained by OCR must be checked visually before it enters the register.
- **Figures**:
  - images `word/media/*`, with their caption and their paragraph;
  - native charts `word/charts/chartN.xml`, with their embedded workbooks;
  - PDF figures, rendered at 200 dpi.

  EMF/WMF images render poorly in LibreOffice: flag them.

## R1 — Fact register, tables, contradictions

1. **Fact register.** Produce `registre_<ref>.jsonl` and a .md view, with one line per fact:
   ```json
   {"id":"T2-045","type":"valeur|terme|définition|décision|méthode|seuil|effectif|date|conclusion|recommandation|limite|question_ouverte",
    "enonce":"…exact…","valeur":"12,7","unite":"%","perimetre":"…","section":"4.2","loc":"§812 | p12-l34","page":12}
   ```
2. **Data tables.** A data table is a `TAB` fact, extracted into `tables/<ID>.csv`: merged cells unfolded, units and scope read in the header, the caption or the note, then copied. A cell is cited like this: `[T2-TAB-03:l4c2]`.
3. **Consolidated header** (`_entete_consolide.md`), in five parts:
   - **A.** Key facts.
   - **B.** `CR-xx` contradictions (two sourced statements, ★ wording) and `REV-xx` revisions.
   - **C.** Internal inconsistencies of each source.
   - **D.** Precedence by subject.
   - **E.** Structuring facts that appear in only one source whereas they would be expected in several.

## R2 — Scoping with the author, in a single series of questions

Send `questionnaire_auteur_v1.md` **before the outline**. Redoing the writing is expensive; a question costs a minute.

**Scoping**
- Subject and title, audience, language, target length.
- Deliverable format: .docx by default if the author works in Word with tracked changes and comments, which the review and correction skills require. If the author did not ask for Word and a native document format is available, ask them to choose.
- Template: a .docx template if there is one.
- Rule 4: replacement or not of the sub-reports.
- Document number and status.

**Decisions D1…Dn**, each with a ★ option and another option:
- the arbitration of each `CR-xx`;
- the approval of each `CALC-xx`;
- the handling of each figure: (a) reused as is, or (b) redone from the `TAB`/`CALC` data alone, with a script kept. A redone figure that aggregates several sources is a `CALC`;
- terminology, structure and level of technical detail.

**Information F1…Fn**: what is missing from the sources (persons responsible, dates, compositions, identifiers), and what will be done without an answer.

**Unanswered questions**: their handling is recorded in `decisions_auteur_v1.json`, key `sans_reponse`.

**Wait for the answers before R3.** If the author says to continue, or does not answer:
- form choices: ★ recommendations;
- `CR`, `CALC` and missing information: visible markers `[À ARBITRER CR-xx]` ("to be arbitrated") or `[À COMPLÉTER : …]` ("to be completed: …");
- the deliverable carries the status `PROJET – décisions non validées` ("DRAFT – decisions not validated") on the cover page and in the header;
- the choices made by default are listed at the top of the log.

Record the answers word for word. New information from the author becomes the fact `AUT-nnn`.

## R3 — Detailed outline and conventions

1. **Outline.** `plan_detaille_v1.md` gives, for each section: its title, its objective for the reader, the IDs of the facts it uses, its tables and figures, its cross-references and its indicative length.
   - **Structure**: cover page (with the mention of replaced documents chosen according to rule 4); Summary; body; limitations; expected decisions and open questions; conclusion; glossary; bibliography; appendices.
   - **Constant template per chapter**, adapted to the genre:
     - technical or process report: Objective / Inputs / Outputs / Method / Application / Interpretation;
     - activity or annual report: Highlights / Indicators (table) / Gaps against targets / Risks / Outlook;
     - briefing note: Finding / Analysis / Recommendation.
2. **Coverage.** Each key fact (A) and each conclusion or recommendation of the sources is placed in a section, or set aside with its reason.
3. **Conventions** (`conventions.md`):
   - typography of the language (in French: space before `: ; ? !`, guillemets `« »`, decimal comma) and SI units;
   - numbering "Table n.k", "Figure n.k" (A.k in an appendix), captions using SEQ fields;
   - equations, only if the sources contain some: numbering (n.k) in parentheses and presentation agreed with the author;
   - a single terminology, aligned with the glossary;
   - acronyms.
4. **Outline validation.** Submit to the author a summary of 10 to 20 lines with the file, then integrate their feedback into `plan_detaille_v2.md`. If they do not reply, continue with v1 and say so at the top of the log.

## R4 — Writing by blocks

Each block (you, or one sub-agent per block launched in parallel) receives: the outline, the conventions, the glossary, the decisions, the register (to be consulted with Grep) and the source texts of its scope. It writes only `section_<k>.md`.

**Writing instructions:**
- Each sentence or cell that carries a fact ends with its identifiers: `[T2-045]`, `[CALC-003]` or `[AUT-002]`. Structural elements without a fact (section numbers, period years) may be tagged `[STRUCT]`.
- Values are copied exactly from the register. Only the decimal separator may be converted. Any other conversion (unit, %, figures written out in words) requires a `CALC`.
- No information outside the register and the decisions. What is missing receives the handling provided in `sans_reponse` and a line in `questions_ouvertes.jsonl` (id, section, question, handling). If the marker is refused, the passage is omitted and the omission recorded.
- Follow the template and the conventions. Write equations in LaTeX, in a dedicated block, with their number and caption.
- At the end of the file, list the outline's facts that were not used and the cross-references to other blocks.

Write the **Summary** and the **Conclusion** yourself, last, from the finished sections: their figures must be those of the body. Also write the glossary and the bibliography.

## R5 — Assembling the .docx

First read the SKILL.md of the docx skill.

1. Gather the tagged text into `contenu_balise_vN.md`. **Keep this file**: it serves as proof in R6. The tags are removed (or turned into references, according to rule 4) only in the assembled text.
2. Choose the assembly chain depending on whether a template exists:
   - **With a .docx template:** `pandoc contenu.md --reference-doc=gabarit.docx --toc` gives the template's styles, native OMML equations and the table of contents as a field. Finish with lxml post-processing: cover page, equation numbers with tab stops (center at half the text width, right at the full width), SEQ captions. docx-js cannot open an existing template.
   - **Without a template:** use docx-js, or pandoc with its default reference.
     - Layout: A4, 2.5 cm margins, native styles Heading 1 to 3 (needed for the table of contents) and Caption, 11 pt sans-serif font, page numbers.
     - Equations with docx-js: place markers `{{EQ:k}}`, then replace them in `document.xml` with pandoc's OMML, corrected according to the recipe of `application-corrections-rapport` (order of the `m:dPr`, `m:sty`/`m:nor` elements), without `w:ins`.
     - Cover page: only the known fields. Invent neither a logo nor a number.
3. Figures: according to the decision of R2, the original image or the figure redone by script, with its numbered caption and the mention of its source, according to rule 4.
4. Traceability matrix: section, sentence or cell, ID, source, §/page, value.
5. Produce trials (`_essai_N.docx`). The deliverable goes into `07_livrables/` only after R6.

## R6 — Verifications

**Concordance** (script, result in `concordance_vN.json`), in three checks:
- (a) each number in a tagged sentence or cell equals, after normalization (spaces, decimal separator, sign, %), the value of one of the cited IDs;
- (b) every untagged number is listed, except those on an explicit whitelist (section, table and page numbers, `[STRUCT]`). Each one is then removed, or sourced, or submitted to the author;
- (c) the text of the final docx equals `contenu_balise_vN` stripped of its tags, paragraph by paragraph.

**Internal consistency:**
- the figures are identical across the Summary, the body, the tables and the conclusion;
- the terminology is unique;
- each acronym is defined at its first occurrence;
- the numbering is continuous;
- each cross-reference points to an existing target.

**Coverage** (`couverture_vN.md`): the key facts and the conclusions of the sources are present, or set aside with their reason.

**Independent verification** by 1 or 2 fresh sub-agents:
- They receive the text extracted from the trial (`_paragraphes.jsonl`, according to phase 0 of the review skill) and the **sources themselves**.
- They check: 100% of the sentences of the Summary and the Conclusion, 100% of the `CALC`, and at least 20% of the other tags, comparing the meaning of each sentence with the source's statement. If the discrepancy rate exceeds 5%, extend the check to all the tags.
- They also verify clarity for the audience, structure, language and typography.
- Their findings go into `verification_independante_N.json`, in the format of the skill `revue-critique-rapport`. Correct, then reassemble.

**Technical integrity:**
- `validate.py` of the docx skill;
- PDF rendering and visual check of the cover page, one page per part, and the tables;
- an empty table of contents in the LibreOffice rendering is normal: only check that the `TOC` field is present;
- reread the equations with `pandoc -t latex`;
- SHA-256 sums of the sources unchanged.

## R7 — Delivery

In `07_livrables/`:
1. `<nom>_v1.docx`.
2. `Matrice_tracabilite_v1.md`, or as `.xlsx` if it is long: one line per fact used.
3. `Journal_redaction_v1.md`, which contains:
   - the sources, their versions and the precedence;
   - the decisions applied and the choices made by default;
   - the contradictions arbitrated and the revisions;
   - the approved calculations;
   - the questions still open, with their location;
   - the results of the verifications and their limitations;
   - the points of attention: update the table of contents and the fields in Word (F9), document number, figures to redo.

Send the docx and the log, and mirror them into the user's folder if the session is linked to it. End with a message of 3 or 4 lines: what was produced, the open questions, the checks to make in Word.

If the author or a third party must proofread the report, a critical review against the sources (skill `revue-critique-rapport`) and then the application of the corrections (skill `application-corrections-rapport`) can follow, as an option.
