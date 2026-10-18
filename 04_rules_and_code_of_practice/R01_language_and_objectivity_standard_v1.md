# R01 — Language and Objectivity Standard for Documents, Instructions and Agent Outputs

**Status:** Authoritative rule. Human-authored (project owner), 24 September 2026. Version 1.
**Applies to:** every project document, every system instruction given to an agent, and every agent-produced report, plan, packet, blocker, incident record and deliverable. The text was issued as a review instruction for the proposal; it is retained here as the standing standard for all written material in the organization.
**Enforcement:** by review (human at Stage 1; QA agents at Stage 2 and later, with human audit) using the eight-category audit of §2 below; the first application is recorded in `03_audits_and_reviews/03_objectivity_audit_v1.md`.
**Amendment:** by a new version file; this file is not modified.

---

## 1. Text of the rule (verbatim)

Review the entire proposal for subjective, emotional, rhetorical, or value-laden language. Identify and revise any wording that depends on personal preference, emotional interpretation, aesthetic judgment, or an implicit value judgment rather than an objectively defensible technical criterion.
Avoid terms such as “boring,” “clever,” “elegant,” “clean,” “obvious,” “simple,” “powerful,” “robust,” “nice,” “good,” “bad,” “ideal,” “best,” or similar terms unless they are explicitly defined using measurable or verifiable criteria.
Do not describe a technical approach using subjective characterizations. Instead, express the underlying requirement in objective terms such as maintainability, complexity, resource consumption, reproducibility, reliability, operational burden, testability, or documented performance.
For every statement that could be interpreted as subjective, ask: “What objectively observable property is this statement intended to describe?” Replace the subjective wording with that property.
Do not introduce new opinions, preferences, recommendations, or evaluative judgments while performing this review. Preserve the original technical intent while making the language precise, neutral, measurable where possible, and independently interpretable by different readers.
Flag any remaining statement whose interpretation could reasonably vary depending on the reader's personal preferences or emotional response.

## 2. Second-pass audit (verbatim)

Perform a second-pass objectivity audit after completing the revision. The audit must specifically check for:

1. Subjective or emotionally loaded terminology.
2. Unquantified evaluative claims.
3. Implicit preferences presented as technical requirements.
4. Metaphors or informal expressions that could have multiple interpretations.
5. Claims such as “better,” “simpler,” “more efficient,” or “more appropriate” that do not specify the criterion or evidence supporting the comparison.
6. Anthropomorphic descriptions of software or AI components.
7. Language that expresses approval, disapproval, enthusiasm, skepticism, or aesthetic preference.
8. Statements that cannot be verified, reproduced, or evaluated using an explicit criterion.

For each occurrence, either replace it with an objective formulation or explicitly define the criterion that makes the statement evaluable.
The final proposal should read as a technical specification or engineering document, not as persuasive, promotional, conversational, or opinion-based writing.
