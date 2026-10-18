# Agentic_Project — workspace index

Project: a persistent, human-governed organization of AI agents (working name AOP): live agents on a constitution-bound hierarchy, entered through team (TWE) and individual (IWE) work environments from a control-plane GUI, planning under the human's approval and operating continuously. This file is the index of the workspace; it is updated whenever a file is added, moved or superseded.

This is the public edition of the workspace. It contains the governance kernel (D5), the rules (D6), the security sections of the development plan (D3) and the capability security review. The source documents (D0–D2), the rest of the development plan (D3), the prototype specification (D4), the platform (D7), the other audits and reviews, and the earlier kernel versions are not included; references to them in the documents below point to that material.

## Folder structure

```
Agentic_Project/
  README.md                       this index
  01_development_plan/            D3: security sections of the project development plan (§6.6, §7.2–§7.4)
  03_audits_and_reviews/          capability security review (R04 → implementation and tests)
  04_rules_and_code_of_practice/  D6: human-authored rules for the agents (R01–R06), stored verbatim; normative source of D3 §6.6, §7.5–§7.9 and of the agent specification
  prototype/                      D5: runnable seed kernel, current version
```

Rules: no file is overwritten; a change produces a new versioned file (`_v1.1`, `_v2`, …) or a new version folder. The exception is this index, which is updated in place because it describes the current state of the workspace. The current version of each document is listed below; earlier versions remain in place for history. Reviews and audits are numbered from 03 onward in `03_audits_and_reviews/`.

## Documents and current versions

| Ref | Current file | Earlier versions | Content |
|---|---|---|---|
| D3 | `01_development_plan/01_project_development_plan_v1.6_security_excerpt.md` | — | Excerpt of the development plan: security architecture (§6.6), threat model mapped to the OWASP Top 10 for agentic applications (§7.2), control protocols by stage (§7.3), safety case structure (§7.4) |
| D5 | `prototype/seed_kernel_v2.7/` | not included | Governance kernel for changes to the platform's code (default-deny function calls, literal-phrase approvals, audit chain, halt, police pipeline, local models, control panel); the mechanism of Stage C in D3 §4.1, not the human's interface; 91 tests |
| D6 | `04_rules_and_code_of_practice/` — `R01_language_and_objectivity_standard_v1.md`, `R02_operating_model_and_disciplined_autonomy_v1.md`, `R03_evidentiary_standard_v1.md`, `R04_capability_security_model_v1.md`, `R05_service_orientation_and_professional_identity_v2.md` (v1 retained), `R06_professional_judgment_feasibility_risk_and_alternatives_v2.md` (v1 retained), `README.md` | — | Rules and code of practice for the agents, verbatim as issued, with headers and amendments |
| — | `03_audits_and_reviews/06_capability_security_review_v1.md` | — | Integration of R04 (kernel v1.3 → v2.0): section map, AC-01…AC-30 and I1–I18 to tests, limits |

Note on this edition: in the full workspace the kernel's governed workspace is the platform (D7); here it is the local folder `prototype/seed_kernel_v2.7/workspace` (`workspace_dir` in `constitution.toml`).

## Where to start

The rules are in `04_rules_and_code_of_practice/README.md`; R04 is the security model the kernel implements: nothing is permitted unless explicit authority has been granted, and the model is a requester, never an authority. The kernel (D5) governs changes to the platform's code and is started with `prototype/seed_kernel_v2.7/Start AOP Kernel.bat` (Windows; it checks for Python 3, installs the one dependency, runs the self-tests on first start and opens the control panel at http://127.0.0.1:8765/), or from the command line with `python -m kernel ...`. `prototype/seed_kernel_v2.7/README.md` explains its architecture; `tests/test_security.py` holds the security tests mapped to R04's acceptance criteria and invariants (see the review in `03_audits_and_reviews/`); `cd prototype/seed_kernel_v2.7 && python -m pytest` runs the whole suite. The security architecture, threat model, control protocols and safety case are in `01_development_plan/`.

## Authorship

I designed the framework and wrote its rules (R01–R06), chose the architecture and the code structure, and directed the development in short, versioned iterations. The code was written by AI coding assistants working under these rules and this structure.
