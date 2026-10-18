# CAPABILITY SECURITY MODEL — INTEGRATION REVIEW (R04; kernel v1.3 → v2.0; D3/D4 v1.3 → v1.4)

**Version:** 1.0 — 24 September 2026
**Rule integrated:** R04 (`04_rules_and_code_of_practice/R04_capability_security_model_v1.md`), stored verbatim.
**Scope:** `prototype/seed_kernel_v2.0/` (new modules `authz.py`, `twe.py`, `police.py`; rewritten `loop.py`, `cli.py`, `audit.py`; `permissions.toml`; `tools/`), D3 §6.6 and SR-24…SR-31, D4 B.5.14–B.5.19.

## 1. Architectural changes from v1.3

| v1.3 | v2.0 |
|---|---|
| The proposer's output was a proposal document; the kernel interpreted its status and acted on files, blockers and approvals directly. | The proposer's output is one function call. `Kernel.dispatch(ctx, function, args)` is the only path from model output to any effect. |
| Authorization was implicit: the kernel applied blacklist rules (denied globs, patterns) to a proposal. | Authorization is positive: `permissions.toml` grants capabilities (permission + scope) per principal; a function executes only if the caller holds the required permission with a scope covering every resource; anything else is DENY. The content rules of `policy.py` remain as an additional deterministic check after authorization. |
| Identity was implicit (the kernel knew it was talking to "the model"). | `KernelRuntime` mints `AgentContext` objects with a private token; the engine accepts no other identity source; identity-bearing arguments are ignored or denied. |
| Approvals were bound to the packet hash; packets lived in a directory the kernel wrote. | Requests are immutable entries in hash-chained TWE logs managed by `TWEService`; approvals are separate records bound to the request payload hash and to a resource scope; apply re-derives the hash from the TWE entry. |
| Denials were reported and audited. | Every function request produces an R04 §19 audit event; every DENY is passed to the deterministic `PoliceEngine`, which classifies it by explicit rules, appends a hash-chained police event, and escalates to the human's TWE for high-severity classes; an optional police LLM records flags only. |
| Fail-closed behaviour on exceptions existed in places. | The engine wraps all checks: any exception, store failure, approval-service failure, unknown resource or unexpected state → DENY with reason `authorization_error` (or the specific code). |

## 2. R04 section → implementation

| R04 § | Provision | Implementation | Test(s) |
|---|---|---|---|
| 1 | Default deny; positive authorization | `AuthorizationEngine._authorize`: capability and scope checks; no allow path without an explicit grant | AC-01, AC-02, AC-03, I1, I16 |
| 2 | Explicit machine-readable capabilities | `PERMISSIONS` constants; `Capability(permission, scope)`; `permissions.toml` | AC-08 |
| 3 | No ambient authority; narrow functions | Registry exposes only `get_authorization_profile`, `read_workspace_tree/file`, `read_twe`, `propose_patch`, `request_action`, `report_blocker`, `abstain`, `record_approval`, `apply_approved_request`, `run_tests`, `read_audit`, `read_police`, `police_llm_review`; no `write_file`, `execute`, `open_socket` | AC-23, `test_agent_never_receives_storage_paths` |
| 4 | Function calls are the interface; call ≠ authorization | `Kernel.dispatch`; `_parse_call` maps model output to one call | end-to-end tests |
| 5 | Identity attached by runtime; arguments never identity | `KernelRuntime.context_for`; `IDENTITY_ARGS` handling | AC-04, AC-05, I2, I7 |
| 6–7 | Non-LLM, inspectable authorization | Engine is pure code; `checks` list records the path taken; no model call anywhere in `authz.py` | all security tests |
| 8 | Scoped capabilities | `Capability.covers`; resource extractors per function; all resources must be covered | AC-07, I3 |
| 9 | Trust/autonomy ≠ authority | Agent record and activity counters are never read by the engine | I17 |
| 10–11 | TWE via functions only; append-only | `TWEService` (append, read copies, verify; no modify/delete); `read_twe` returns deep copies, no paths | AC-10, AC-11, AC-13, I6, I12 |
| 12–13 | Approval separate and bound to exact request | `record_approval` writes a hashed record with `request_hash` and `scope`; apply checks request existence, immutability (stored vs recomputed hash), approval hash, decision, scope, approver authority, self-approval | AC-14, AC-15, I4, I13, self-approval and expiry tests |
| 14 | Authorization profile visible | `get_authorization_profile`; included in every proposer prompt | AC-08, prompt test |
| 15 | Evidence-based operation | `_evidence_ok`: block required; sourced needs source; derived needs premises; hypotheses/unknowns do not count | AC-16, AC-17, I5 |
| 16, 33 | Consequential operations by consequence | Consequence classes in constitution and prompt; `apply_approved_request` marked consequential (evidence + approval); no external-action function exists; `request_action` records only | AC-16, `test_model_cannot_apply_or_approve_through_calls` |
| 17 | Kernel is final enforcement | `apply_approved_request` executes only after the engine's request-state, evidence, approval and scope checks | AC-06, AC-14, AC-15 |
| 18 | Fail closed | `authorize` try/except → DENY; unknown identity/function/resource/request → DENY; store failure and approval-service failure → DENY | AC-24, AC-25, I14, I15 |
| 19 | Audit fields | `AuditLedger.record(...)` with agent_id, session_id, function_id, resource_id, request_id, approval_id, authorization, denial_reason, input_hash, output_hash | AC-18, AC-19 |
| 20–21 | Failed requests preserved; failure ≠ misconduct | DENY → audit → `PoliceEngine.inspect`; classification names the boundary, not intent; findings remain human decisions (D3 §7.7) | AC-20, AC-21 |
| 22–26, 28 | Police subsystem: deterministic engine + LLM; explicit police capabilities; police audited; police cannot authorize | `police.py`; `police` principal capabilities in `permissions.toml`; `police_llm_review` function; no reference from police to engine; police events hash-chained | AC-21, AC-22, AC-23, I9, I10 |
| 27 | Agent authorization awareness | Profile in prompt; refresher item 7 | prompt test |
| 29–30 | Tamper-evident audit; no self-modification of history | Hash chains for audit, police and each TWE; no delete/modify functions; agents lack write access to `state/` | AC-28, AC-29, I11 |
| 31 | OS enforcement | `tools/setup_os_isolation.sh`, `tools/check_os_isolation.py`; sandbox wrapper for tests | AC-09, AC-26, AC-27 (deployment checks) |
| 32 | Reasoning ≠ authority | Model output enters only through `_parse_call`; no field of it reaches the engine as authority | I17 |
| 34–35 | Failure classes; no independent repair | Incident kinds and findings (D3 §7.7); the only automatic recovery is checkpoint restoration | rollback test |
| 36 | Auditable by one engineer | Security-critical path: `authz.py` (≈330 lines), `dispatch` (≈40 lines), `twe.py`, `police.py` | — |
| 37–38 | Core invariant; final model | Separation: model requests, engine authorizes, handlers execute, ledger records, police investigates | whole suite |

## 3. Acceptance criteria (R04 §39) → tests

| AC | Test | Status |
|---|---|---|
| AC-01 | `test_ac01_unassigned_function_is_denied` | pass |
| AC-02 | `test_ac02_new_capability_denied_until_assigned` | pass |
| AC-03 | `test_ac03_unknown_function_denied_audited_policed` | pass |
| AC-04 | `test_ac04_agent_id_in_arguments_is_ignored_or_rejected` | pass |
| AC-05 | `test_ac05_missing_or_forged_context_is_denied` | pass |
| AC-06 | `test_ac06_permission_boundary_read_but_not_apply` | pass |
| AC-07 | `test_ac07_resource_scope_boundary` | pass |
| AC-08 | `test_ac08_similar_capability_does_not_imply_another` | pass |
| AC-09 | `tools/check_os_isolation.py` in the deployment environment (requires the two-user layout) | deployment check; not unit-testable in CI without root |
| AC-10 | `test_ac10_twe_access_only_through_functions_and_no_handles` | pass |
| AC-11 | `test_ac11_workspace_permissions_do_not_grant_twe` | pass |
| AC-12 | `test_ac12_request_ids_unique` (10,000 requests) | pass |
| AC-13 | `test_ac13_submitted_request_is_immutable` | pass |
| AC-14 | `test_ac14_approval_bound_to_exact_request` | pass |
| AC-15 | `test_ac15_narrow_approval_cannot_authorize_broader_scope` | pass |
| AC-16 | `test_ac16_missing_evidence_denies_before_execution` | pass |
| AC-17 | `test_ac17_unverified_information_cannot_satisfy_evidence` | pass |
| AC-18, AC-19 | `test_ac18_ac19_every_request_audited_with_identity` | pass |
| AC-20 | `test_ac20_denied_request_survives_restart` | pass (kernel re-instantiation = process restart equivalent) |
| AC-21 | `test_ac21_every_authorization_failure_triggers_police` | pass |
| AC-22 | `test_ac22_police_llm_cannot_authorize` | pass |
| AC-23 | `test_ac23_police_cannot_modify_audit_or_its_own_permissions` | pass |
| AC-24 | `test_ac24_permission_store_failure_denies` | pass |
| AC-25 | `test_ac25_approval_service_failure_denies` | pass |
| AC-26, AC-27 | `tools/check_os_isolation.py` | deployment check |
| AC-28 | `test_ac28_historical_modification_detectable` | pass |
| AC-29 | `test_ac29_audit_and_police_chains_survive_restart` | pass |
| AC-30 | `tests/test_security.py` (34 tests) + `tests/test_kernel.py` (20 tests): 54 pass | pass |

Invariants I1–I18: I1 (AC-01/02), I2 (AC-05), I3 (AC-07), I4 (AC-14/15, rejected/expired tests), I5 (AC-16/17), I6 (AC-10/11 architectural; AC-09 deployment), I7 (AC-19), I8 (AC-18/20), I9 (AC-21), I10 (AC-22), I11 (AC-23/28), I12 (AC-13), I13 (AC-14), I14 (`test_i14_engine_exception_denies`), I15 (AC-24/25), I16 (AC-02), I17 (`test_i17_trust_counters_do_not_create_authority`, `test_model_cannot_apply_or_approve_through_calls`), I18 (AC-10 architectural; AC-26/27 deployment).

## 4. Limits and open items

The unit suite verifies application-level enforcement. OS-level isolation (AC-09, AC-26, AC-27, I18's OS half) is verified by `tools/check_os_isolation.py` after `tools/setup_os_isolation.sh`, which requires root and a POSIX host (WSL, Linux VM or Docker); this is recorded as a deployment gate in D4 B.8 and in the safety case. The proposer LLM has no OS identity on the machine (it is an HTTP endpoint); the only agent-controlled code executed locally is the test command, which runs under the sandbox wrapper and uid. Redis is not used; all security state is file-based with hash chains, which satisfies R04 §29's append-only and tamper-evident properties for a single-machine deployment. `request_action` records generic action requests but no executor exists for any action type other than `patch`; every external-action permission (`EXTERNAL_COMMUNICATION`, `EXTERNAL_SYSTEM_WRITE`) is defined and assigned to no principal. `MODIFY_KERNEL`, `MODIFY_CONSTITUTION` and `MODIFY_PERMISSIONS` are defined, assigned to no principal, and have no registered function; those files are edited by the human outside the kernel, and the change is recorded by hash at the next start.

---
*End of `03_audits_and_reviews/06_capability_security_review_v1.md`.*
