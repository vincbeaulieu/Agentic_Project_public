# Security architecture, threat model, control protocols and safety case

Excerpt of the project development plan (version 1.6): sections 6.6, 7.2, 7.3 and 7.4 only. The rest of the plan is not included. Identifiers such as SR-07, FR-TOOL-1, D4, D5 or §7.7 refer to parts of the full plan.

---

### 6.6 Security architecture: default-deny capabilities, function-call interface, police subsystem (rule R04)

Rule R04 (`04_rules_and_code_of_practice/R04_capability_security_model_v1.md`) governs the security architecture. Its central principle is that nothing is permitted unless explicit authority has been granted, implemented as a property of the kernel rather than as an instruction to a model. The model is a requester and reasoning component; it is not an authority, identity provider, permission interpreter, security boundary or audit authority.

**Default deny and explicit capabilities.** Authority is represented as machine-readable capabilities, each a permission with a resource scope (for example `PROPOSE_PATCH → workspace/src/**`), declared per principal in `permissions.toml`, a human-only file whose hash is recorded in the audit chain. A function executes only if the caller holds the function's required permission with a scope covering every resource the call touches. A function that is not registered is unknown and denied; a registered function whose permission no principal holds is denied for everyone, so new functionality is unavailable until an explicit grant is made. Trust and autonomy records, prior approvals, similarity to earlier requests, and confidence never create authority; the engine does not read them.

**Function-call interface and authenticated identity.** Agents reach protected state (TWE logs, approvals, audit, police records, permissions, constitution, workspace) exclusively through registered kernel functions. The runtime attaches the authenticated principal to every call; function arguments are never a source of identity, and an identity-bearing argument that differs from the context is denied and recorded. No generic primitive (write file, execute, open socket, modify database, change permissions) is exposed. The authorization profile is available to each agent as a function and is included in every prompt so that agents do not discover their permissions by probing; the kernel re-checks on every call regardless.

**TWE service, immutable requests and bound approvals.** TWE logs are append-only, hash-chained, and written only by the TWE service; reads return copies and never a path or handle. A request becomes an immutable entry with a unique id and a payload hash; a correction is a new entry referencing the previous one. Approvals are separate records bound to the request id, the request hash, the approver and a resource scope; at apply time the kernel verifies that the request exists, that its stored and recomputed hashes match, that the approval's hash matches, that the approver holds `APPROVAL_APPEND`, that the approver is not the requester, that the approved scope covers every resource, and that the approval is unexpired. An approval for one request cannot authorize another; a narrow approval cannot authorize a broader operation; modifying a request after approval invalidates it.

**Fail closed.** Unknown identity, unknown function, missing permission, missing or ambiguous scope, missing or invalid approval, hash mismatch, missing evidence, unknown resource, permission-store or approval-service failure, and any exception in the authorization path result in DENY. Uncertainty is never interpreted as permission.

**Audit and police.** Every function request produces an audit event with the fields of R04 §19 (agent, session, function, resource, request, approval, authorization result, denial reason, input and output hashes), in a hash-chained ledger that agents cannot write. Every denial is passed to a deterministic police engine that classifies it by explicit, versioned rules (unauthorized function, unauthorized scope, invalid request, invalid or expired approval, hash mismatch, identity mismatch, protected-resource access, repeated denied operations, authorization-service failure), appends a hash-chained police event, and escalates high-severity classifications to the human's TWE. An optional police LLM reviews windows of audit events for behavioural patterns and records flags; no code path connects its output to the authorization engine. Police principals hold only the explicit capabilities `AUDIT_READ`, `POLICE_EVENT_APPEND`, `INVESTIGATION_CREATE`, `INVESTIGATION_READ`, `ESCALATION_REQUEST`; no function deletes or modifies audit or police history. A denial establishes that an authorization boundary was reached; it does not by itself establish misconduct, and findings on judgment remain human decisions under §7.7.

**Operating-system enforcement.** The application-level engine is not the only boundary. The deployment layout places `kernel/`, `constitution.toml`, `permissions.toml` and `state/` under a kernel user with modes 700/600, and runs agent-controlled code (the test command) under a separate sandbox user or container; `tools/check_os_isolation.py` verifies the layout. The effective authority of an agent is the intersection of the OS layer, the kernel permission layer and the capability-restricted API.

**Auditability by one engineer.** The security-critical path is `authz.py`, `Kernel.dispatch`, `twe.py` and `police.py` in kernel v2.0; the trace of a request (identity → capability → scope → request state → evidence → approval → policy → result → audit → police) is recorded in each audit event's `checks` field.

---


### 7.2 Threat model (OWASP ASI01–ASI10 mapped to controls)

| Threat | Instance in this project | Control |
|---|---|---|
| ASI01 Agent goal hijack | An ingested email or web page contains instructions | SR-07; literal-phrase approvals; monitor; SR-12 |
| ASI02 Tool misuse | A tool is used to read files outside scope | Tool gateway allow-lists; path jail; data classes per tool |
| ASI03 Identity and privilege abuse | An agent uses a credential assigned to another | Per-agent credentials in a vault, injected by the gateway; absent from prompts |
| ASI04 Supply chain | A downloaded MCP server or agent definition contains unwanted behavior | Hash pinning, review, qualification in shadow mode (FR-TOOL-1) |
| ASI05 Unexpected code execution | Model-generated code executes on the host | Sandboxes; fixed commands; no model-generated string is executed (D5) |
| ASI06 Memory and context poisoning | An incorrect statement enters the project knowledge base | Evidence entity with provenance; AI summaries distinguished from originals; reviewed memory |
| ASI07 Insecure inter-agent communication | One agent presents itself as a Director | Single logged bus; signed messages; collaboration edges approved by supervisors |
| ASI08 Cascading failures | A defective plan step propagates | Per-team budgets; bounded retries; halt hierarchy; checkpoints |
| ASI09 Human-agent trust exploitation | A digest omits or misstates an action | SR-06 |
| ASI10 Rogue agents | An agent continues operating outside policy | Registry status; re-qualification; idle detection; emergency shutdown; FREEZE |

### 7.3 Control protocols by stage

Stage 1: every mutation is reviewed by a human; rule-based screening rejects violations before the review step. Stage 2: trusted monitoring with deferral — a trusted model (smaller, different family) scores each proposal; proposals in the low risk class below a suspicion threshold are applied and logged; proposals above the threshold are deferred to the human; a configured fraction of applied proposals is audited by the human at random. Stage 3: untrusted monitoring may be added for technical reviews, with the collusion countermeasures described by Nelson et al. (distinct prompts, paraphrasing, honeypot proposals with known expected verdicts). The protocol in force is recorded in the constitution and its measured performance (honeypot detection rate, audit findings) is reported.

### 7.4 Safety case structure

The safety case (`docs/safety-case.md`, template in D4) has the top-level claim: "the organization cannot perform a reserved action or write outside its granted scope without a human decision, and halts when a halt is requested." Sub-claims (halts are honored; approvals cannot be forged; sandboxes contain execution; monitors do not collude; budgets trip) each carry evidence (test names, control-evaluation results with confidence intervals, audit statistics, adversarial test results) and an explicit unsolved-problems section. Stage promotion requires the safety case to be updated first.


