---
name: "revue-critique-rapport"
description: "Rigorous critical review of a final report (.docx) against its authoritative reference reports: fact register, figure concordance, independent verification, Word comments without touching the text."
---

# Critical review of a final report against its reference reports

The author receives three things:
- **an annotated copy** of their report: Word comments anchored to the exact word, the text unchanged;
- **a prioritized review report**;
- **a fact register of the references**, which makes it possible to verify each finding.

Rigor rests on four habits:
- **each finding is proven** by a precise source;
- **nothing is modified** in the text;
- **everything is versioned**;
- **an independent reviewer** double-checks the serious findings.

## Inputs

**Minimum required:**
- the final report (.docx);
- at least one reference report (.docx, .pdf or .md), which is authoritative.

**To ask for at the start, if absent and if it changes the review:**
- the audience (Management, technical team, authority);
- which reference takes precedence on which subject.

Any particular instruction from the user takes precedence over this procedure. Copy it word for word into `journal.md` and into the sub-agents' instructions.

**Language.** The comments and the review report are written in the user's language. The typography checked is that of the report's language. A reference in another language, with a different decimal separator, does not create a value discrepancy ("0.89" = "0,89").

## Scaling the effort

| Size | How to work |
|---|---|
| Report of fewer than ~25 pages, or a single reference | Register and review done by yourself, in one block; phases 3 and 4 merged |
| Larger | One sub-agent per reference (phase 1) and per block of 10 to 15 pages (phase 3), launched in parallel |
| Reference of more than ~80 pages | One sub-agent per chapter of that reference |

Without a sub-agent tool, work in sequence and note it in the log. In every case, keep the **independent verification** of phase 5: by a fresh sub-agent, or failing that by a separate, documented second pass.

## Rules and reasons

1. **The references are authoritative.** An explicit contradiction with a reference is presumed to be an error in the report, unless the report justifies the difference. In that case, flag it anyway and ask for the difference to be owned and sourced. A fact **with no equivalent** in the references is not an error: it is a "not verifiable in the corpus" finding, Minor or Major if it is structural, which asks for a source.
2. **Contradiction BETWEEN references (CR-xx): do not decide.** The precedence rule serves only to choose the comparison value for alignment findings. A CR-xx remains a question for the author. You may attach the recommended source (★), without applying it.
3. **Only add comments.** The text, the formatting, the revisions and the existing comments do not change. The author must be able to trust their copy, and phase 6 proves it. Technical exceptions are tolerated, each one recorded in the log:
   - the comment styles, if they are absent;
   - a `paraId` and a `commentEx` entry added to an existing comment that has none, so that it can be answered in its thread.
4. **Never overwrite.**
   - Deliverables are named `<nom>_revue-critique_v1.docx`, then v2, v3 at each revision, and likewise `Revue_critique_<nom>_v1.md`.
   - Originals are read-only (`chmod a-w`).
   - Check the SHA-256 sums at the end of each phase.
5. **Compare, do not redo the analyses.** The review compares the report with its references; it does not reproduce their calculations, which cannot be verified without the original data.
   - Checking the figures means checking **concordance**: same value, same unit, same rounding. A difference is flagged as a probable transcription error.
   - Simple arithmetic checks (table total, sum to 100%, unit conversion) belong to internal consistency. A difference there becomes a question, never a corrected value.
   - The **clarity** of the presentation (missing unit, unreadable formula) can always be commented on.
6. **No finding without proof.** Each finding cites:
   - the source: document, section, §index or page/line, register ID, exact value;
   - or `Interne : §x vs §y` ("Internal: §x vs §y").

   If in doubt, the finding becomes a question. Leave no vague comment: say why it is a problem and what to do, with the proposed wording.
7. **New information from the author overrides the references.** Rephrase the findings concerned in a new version, without erasing the previous one.
8. **Keep a trace.** Update `journal.md` at the end of each phase. If the session is linked to the user's computer, mirror the work folder into their folder after each phase, creating the folders first. That folder serves as a durable trace of the work. Send the files only once, when they are finished.

## Work folder

Create the folder next to the input files, in the same parent folder: `travail_revue/`, or `travail_revue_<n>/` if the name already exists.

```
travail_revue/
  00_originaux_copies/    copies (lecture seule) + sha256_originaux.txt
  01_inventaire/          <doc>_paragraphes.jsonl, _texte.md, _structure.md, _pagemap.json, commentaires_existants.json
  02_registre_references/ registre_<ref>.jsonl (+ vue .md), _entete_consolide.md, registre_references.md
  03_blocs/               bloc_<n>.md, bloc_<n>_paraids.tsv, commentaires_bloc_<n>.json, table_des_matieres.md, consignes_sous_agents.md
  04_revues_blocs/        revue_bloc_<n>.json
  05_transversal/         revue_transversale.json
  06_consolidation/       plan_fusion.json, concordance_vN.json, constats_consolides_vN.json, constats_retires_vN.json,
                          verification_*.json, commentaires_inseres_vN.json
  07_livrables/           docx annoté vN, Revue_critique_<nom>_vN.md, verification_integrite_vN.md
  scripts/
  journal.md
```

Create one task per phase in the task list and tick it when it is done.

## Phase 0 — Inventory

1. Copy the originals and compute their SHA-256 sums. In the log, note for each document: title, number, version, date, status (draft or final), language. Also note the tool versions (LibreOffice, pandoc, docx skill).
2. **For each .docx**, parse `word/document.xml` with lxml and produce:
   - `_paragraphes.jsonl`: one record per `w:p`, with global index, part, `w14:paraId`, style, level and exact text (tabs included).
     - Ignore the `w:p` placed in an `mc:Fallback`, otherwise the indexes are duplicated.
     - Find headings by `w:outlineLvl` or by the style **name** (heading n / Titre n), never by an assumed styleId, because styleIds vary with Word's language.
     - Add the footnotes and endnotes (`[N<n>]`), the headers and footers, as well as the text boxes.
   - `_texte.md`: the full text, each line prefixed with `[§index p.page]`. Tables are turned into lines, with `⟨§index⟩` in front of each cell.
   - `_structure.md`: headings, word count per section, tables, figures, captions.
   - `_pagemap.json`:
     - render the PDF with `soffice --headless --convert-to pdf`;
     - match the paragraphs to the pages in order, never going backwards, skipping the table of contents;
     - warn that the pagination may differ from Word's by ±1 to 2 pages.
3. **For each PDF**, first read the `pdf-reading` skill.
   - Extract the text page by page (`pdftotext -layout`) and the tables (pdfplumber, checked against the page image). The marker becomes `[p.<page> l.<ligne>]`.
   - A page without a text layer goes through OCR (text recognition), which is flagged in the log. A value read by OCR and not checked against the image can support only a Minor finding.
4. **Existing comments**: id, author, date, parent (thread), resolved, anchored text, paragraph. If there are none, `commentaires_existants.json` contains `[]`.
5. **Existing revisions** (`w:ins`, `w:del`, `w:moveFrom`, `w:moveTo`, `w:rPrChange`, `w:pPrChange`): count them by author. If there are any, ask which view to reread. By default, it is the "all accepted" view. Never anchor a comment in a `w:del`.

## Phase 1 — Fact register of the references

**One file per reference.** Produce `registre_<ref>.jsonl` (and a readable .md view), with one line per verifiable fact:

```json
{"id":"REF1-045","type":"valeur|terme|définition|décision|méthode|seuil|effectif|date|conclusion|recommandation|limite","enonce":"…exact…","valeur":"12,7","unite":"%","section":"4.2","loc":"§812 ou p12-l34","page":12}
```

- The units and the scope of a table are read in its header, its caption or its note. Copy them into each value.
- Choose a short prefix per reference and announce it.
- At the top of each register, note the title, the version, the date and the SHA-256 sum of the reference.

**Consolidated file `_entete_consolide.md`.** Write it yourself:
- **A.** The consolidated key facts: those taken up by the audience that decides.
- **B.** The contradictions between references, **CR-01…**, with the two statements sourced.
- **C.** The internal inconsistencies within each reference.
- **D.** The precedence rule, subject by subject. By default, the most specialized reference for its subject, then the most recent. A figure restated in a more recent source is a revision, not a contradiction. Any uncertainty becomes a question.

`registre_references.md` gathers the header and the views of the registers. The sub-agents consult it by Grep.

## Phase 2 — Splitting into blocks

Split the report into blocks of about 10 to 15 pages, at chapter boundaries. For each block, prepare:
- `bloc_<n>.md`: the text, preceded by the block's existing comments;
- `bloc_<n>_paraids.tsv`;
- `commentaires_bloc_<n>.json`.

Add `table_des_matieres.md`, then `consignes_sous_agents.md`, from the template at the end of the file.

## Phase 3 — Review by block

Launch one sub-agent per block, all in the same message. Each reads:
- its block;
- part A–D of the register in full;
- the register by Grep, for each value or term in its block;
- the table of contents;
- the existing comments.

It writes only `revue_bloc_<n>.json`.

On return, check by script:
- that each JSON is valid;
- that each `ancre_texte` appears literally in the indicated paragraph. Otherwise, search the neighboring paragraphs (±3), since an anchor shifted by one paragraph is frequent.

## Phase 4 — Cross-cutting review

Look for what a single block does not see:
- a section template that is not followed;
- redundancies between chapters and appendices;
- variable terminology;
- acronyms missing from the glossary;
- important elements of the references absent from the report;
- an imbalance between the parts;
- a mismatch with the audience.

Produce `revue_transversale.json`, in the same format as the block reviews.

## Phase 5 — Consolidation, systematic checks, independent verification, insertion

1. **Merging** (`plan_fusion.json`).
   - The same problem flagged in several places becomes a single finding, placed at its first occurrence, with `Autres emplacements concernés : …` ("Other locations concerned: …") given by readable section.
   - Remove duplicates and trivial items.
   - Recalibrate the severities across the blocks.
   - Removed findings go into `constats_retires_vN.json`, with their reason.
2. **Systematic concordance of the figures** (script).
   - Extract all the numbers in the report (text and tables), excluding section, table and page numbers.
   - Link each one to a register fact (normalized value and unit): `concordance_vN.json`.
   - Examine each number that is unlinked or diverging, and add the missing findings.
   - Mark each key fact A as present in or absent from the report.

   This safety net catches what the reading missed.
3. **Independent verification.**
   - Hand to 1 or 2 fresh sub-agents, who have not seen the review: **all** the Critical and Major findings, all the "absent from the report" findings, and a sample of about 10% of the Minor findings.
   - They have access to the references themselves, not only to the register.
   - Each finding receives a verdict: *confirmed*, *nuanced* (with rewording) or *unfounded* (removed, with the reason).
4. **Consolidation.** Write `constats_consolides_vN.json`. Each finding has a stable `id_constat`, for example B3.12.
5. **Insertion** into a copy of the original (see the recipe below).
   - A `[Note de lecture]` ("reading note") comment at the top: sources, conventions, severities, the user's particular instructions.
   - Then one comment per finding.
   - A reply to an existing comment goes **in its thread**, attached to the root comment.
   - Resolved threads receive no reply, unless requested otherwise.
   - Write `commentaires_inseres_vN.json`: the mapping between finding, Word comment number, paragraph and anchoring mode (exact, neighboring, whole paragraph).

### Comment format

```
[<Catégorie> | <Gravité> | <id_constat>]
Constat : <ce qui pose problème, précisément>
Référence : <doc, section, § ou p./l., ID registre, valeur faisant foi> | Interne : §x vs §y | Sans objet
Correctif proposé : <quoi modifier, avec la formulation suggérée>
Autres emplacements concernés : <section §… ; …>      (si le constat est fusionné)
```

**Categories:**
- `Alignement références` ("Alignment with references")
- `Cohérence interne` ("Internal consistency")
- `Structure`
- `Compréhensibilité` ("Comprehensibility")
- `Éléments formels` ("Formal elements")
- `Suivi commentaire existant` ("Follow-up of existing comment")

**Severity:**
- **`Critique`** ("Critical"): touches a key figure, a decision, a conclusion or a regulatory obligation taken up by the audience that decides, or misleads the reader about a result.
- **`Majeure`** ("Major"): touches a value, a term, a method or a secondary conclusion, or prevents understanding of a section.
- **`Mineure`** ("Minor"): form, cross-reference, numbering, typography, local clarity.
- **`Suggestion`**: optional improvement.

## Phase 6 — Integrity (proof that nothing was touched)

Result in `verification_integrite_vN.md`:
- **Identical text** in all the parts outside comments (`w:t`, `w:tab`, `w:delText`, `w:instrText`, `m:t`).
- **Same structure**: same number of paragraphs, with the same text.
- **Same formatting.** Compare the sequence (pPr, rPr, text) of each paragraph:
  - after merging the adjacent runs that have the same rPr, since anchoring splits runs;
  - ignoring the markers and the comment reference runs.

  List any other difference. Only the exceptions of rule 3 are allowed.
- **Original comments and original revisions** intact: text, threads, authors, dates.
- **Validation** by `python <skill docx>/scripts/office/validate.py <copie> --original <original>`. If the tool is absent, parse all the parts with lxml, check that the identifiers match one another, and flag the limitation.
- **Rendering**: the PDF can be generated, and the pandoc conversion to text is identical to that of the original.
- **Sources**: the SHA-256 sums of the originals are unchanged.

## Phase 7 — Review report

`Revue_critique_<nom>_vN.md` has 11 sections. If a section is empty, write `Sans objet` ("Not applicable").

1. **Executive summary**: overall assessment, priority problems, count of findings by severity and by category.
2. **Methodology and scope**: sources, precedence, the user's instructions, checks done, limitations.
3. **Inconsistencies with the references**, grouped by theme.
4. **Internal inconsistencies.**
5. **Structure and organization**: assessment, revised outline proposed without changing the substance, findings.
6. **Comprehensibility and writing**; **formal elements**.
7. **Elements of the references absent from the report.**
8. **Contradictions between references to be arbitrated**: for each CR-xx, the two sources, a proposed wording and the recommended source (★).
9. **Follow-up of existing comments.**
10. **Prioritized correction plan**:
    - Priority 1: Critical then Major, to be corrected before distribution;
    - Priority 2: Minor, grouped by workstream;
    - Priority 3: Suggestions.
11. **Appendix**: complete list of the comments (Word number, id_constat, section, page, severity, summary).

If the corrections are to be applied afterwards, propose the skill `application-corrections-rapport`. Otherwise, write a standalone correction prompt that specifies: the files, the rules, the decisions made, and the points to submit to the author.

## Revisions requested by the author

When the author provides a clarification, a new rule or a scope, work as follows:
1. Create `corrections_finales_vN.json` and, if needed, `ajouts_vN.json`.
2. Regenerate `constats_consolides_vN.json`.
3. Reinsert the comments **from the original**, to avoid duplicates.
4. Rerun phase 6.
5. Produce the next report `vN`.

The previous versions stay in place. If a remark is short or ambiguous, ask what it targets and where it applies before rewriting dozens of comments.

## Template for `consignes_sous_agents.md`

The file contains, in this order:

- **Role and context**: "You are a senior technical reviewer…", then the purpose of the report, its version, its language and its audience.
- **Inputs, read-only**: the block; the register (part A–D in full, the rest by Grep); the table of contents; the block's comments. State the prefixes and the particularities of each reference: language, decimal separator, domain where it prevails.
- **Rules**: reuse rules 1, 2, 5 and 6, as well as any particular instruction from the user, copied word for word.
- **What to check**:
  - alignment with the references;
  - internal consistency;
  - structure;
  - comprehensibility for the audience;
  - formal elements: cross-references, numbering, captions, [n] references, typography, typos grouped together;
  - existing comments: still relevant, already handled or contradicted, with a proposed reply to the root comment.
- **Requirements**:
  - a repeated problem = a single finding, with `autres_emplacements`;
  - no quota, but justify a block that yields fewer than 5 or more than 50 findings;
  - professional and constructive tone.
- **Output**: a JSON array, one entry per finding:
  ```json
  {"ancre_texte":"5 à 15 mots EXACTS d'un seul paragraphe ou d'une seule cellule, unique si possible",
   "paragraphe_id":"§<index>","type":"nouveau|reponse","id_commentaire_parent":null,
   "categorie":"...","gravite":"Critique|Majeure|Mineure|Suggestion",
   "constat":"...","reference":"...","correctif":"...","section":"<n° et titre>","page":0,"autres_emplacements":["§..."]}
  ```
- **End of task**: validate the JSON with python, check each anchor by Grep, then reply in 6 lines at most (count by severity and the 3 main findings).

## Technical recipe — inserting Word comments without touching the text

Base: the docx skill (read its SKILL.md) and lxml.

**Identifiers**
- The comment's `w:id` = the maximum of all the comment identifiers in the package, plus 1. The maximum is taken over `comments.xml`, `commentRangeStart` and `commentReference`, in all the parts.
- `w14:paraId` and `durableId`: 8 hexadecimal characters absent from the whole package, with a value below 0x7FFFFFFF.
- Each line of the comment is a separate `w:p`, with its own `w14:paraId`.

**Anchoring**
- Look for the anchor after normalizing the text (non-breaking spaces, apostrophes, quotation marks, multiple spaces). If it appears several times, take the first occurrence and note it.
- Split the runs at both boundaries by duplicating the run and its rPr. Split only inside `w:t`, with `xml:space="preserve"` on both halves.
- Never split inside a field (`fldChar begin…end`), an `m:oMath` or a `w:del`. In those cases, widen the boundary to the whole element.
- Place `w:commentRangeStart` before the first run. Then place `w:commentRangeEnd` after the last one, followed by a reference run: an "annotation reference" rStyle followed by `w:commentReference w:id=…`. These markers are placed at run level, including inside a `w:hyperlink`.
- If the anchor cannot be found, try the neighboring paragraphs (±3), then the whole paragraph. Note the mode used.

**Package parts**
- `comments.xml`: `w:comment` element with author, initials and the ISO date in UTC (without milliseconds). The first paragraph carries the `w:annotationRef` run, and the first line is in bold.
- `commentsExtended.xml`: `w15:commentEx` element with the `paraId` of the **last** paragraph of the comment and `done="0"`. A reply carries `w15:paraIdParent`, equal to the paraId of the last paragraph of the root comment. This attribute is what creates the thread.
- `commentsIds.xml`: `w16cid:commentId` element with `paraId` (last paragraph) and `durableId`.
- `commentsExtensible.xml`: `w16cex:commentExtensible` element with the same `durableId` and `dateUtc`.
- `people.xml`: one `w15:person` for the author of the review.
- **If these parts are missing**, create them:
  - declare w, w14, w15, w16cid, w16cex and `mc:Ignorable`;
  - add the Override elements in `[Content_Types].xml`, with the type `application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml` (variants commentsExtended, commentsIds, commentsExtensible, people);
  - add the relationships in `word/_rels/document.xml.rels`: `…/officeDocument/2006/relationships/comments`, `http://schemas.microsoft.com/office/2011/relationships/commentsExtended`, `…/2016/09/relationships/commentsIds`, `…/2018/08/relationships/commentsExtensible`, `…/2011/relationships/people`.
- **Styles**: find the comment styles by their `w:name` (annotation text, annotation reference). If they are absent from `styles.xml`, add them and note it.

**Reply in a thread**
- Place the reply's markers next to the parent's: start just after the parent's start, end just before the parent's end, reference just after the parent's reference.
- If the parent has no range, place only the reference run.

**Package**
- Rewrite the zip keeping the order and the attributes of the entries. Replace only the modified parts.

**Author**
- Use a name distinct from the human author's, for example `Revue critique - Claude` ("Critical review - Claude"), initials RC.

## Delivery

- Send the annotated docx and the review report, and mirror them into the user's folder if the session is linked.
- The final message fits in 3 to 5 lines:
  - the number of findings by severity;
  - the 2 or 3 major problems;
  - the CRs to arbitrate;
  - the limitations (approximate pagination, OCR);
  - the possible next step: apply the corrections.
