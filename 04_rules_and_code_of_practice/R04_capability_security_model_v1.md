# R04 — Default-Deny Capability Security Model, Function-Call Interface, Police Subsystem and Security MVP Criteria

**Status:** Authoritative rule. Human-authored (project owner), 24 September 2026. Version 1.
**Applies to:** the kernel, the runtime, every agent interface, the TWE and approval subsystems, the audit subsystem, the police subsystem, OS-level deployment, and the security acceptance criteria of the MVP.
**Enforcement:** implemented in `prototype/seed_kernel_v2.0/` (authorization engine, function registry, runtime contexts, TWE service, approval binding, police engine, audit schema, security regression suite) and specified in D3 §6.6 and D4 B.5.14–B.5.19; the mapping of each section and acceptance criterion to its implementation and test is in `03_audits_and_reviews/06_capability_security_review_v1.md`.
**Amendment:** by a new version file; this file is not modified.

---

## Text of the rule (verbatim)

The agent should not have direct access to the TWE or approval files at all. It should interact with the kernel through a restricted function-call API.

Design the system around a strict default-deny capability security model, analogous in principle to Unix permission and least-privilege semantics, rather than a permissive application architecture where components receive broad access and are subsequently restricted by a collection of prohibitions.
The central architectural principle is:
Nothing is permitted unless explicit authority has been granted.
This principle must be implemented as a property of the program architecture and kernel, not merely as an instruction to the LLM.
The LLM is a requester and reasoning component. It is not an authority, identity provider, permission interpreter, security boundary, or audit authority.
1. Default-deny architecture
Every operation must begin in the denied state.
An agent does not gain access merely because:

* the operation is technically possible;
* the resource is visible;
* the agent knows the resource exists;
* the operation appears safe;
* the agent has previously performed a similar operation;
* the agent has a high trust score;
* the agent has a high autonomy score;
* the agent believes the operation is necessary;
* no rule explicitly prohibits the operation.

Access exists only when an explicit capability grants it.
The system must therefore use a positive authorization model:

```cpp
if (!has_capability(agent, operation))
    deny();

```

rather than a blacklist model:

```cpp
if (!is_forbidden(operation))
    allow();

```

The security model must remain safe when new functionality is introduced.
If a developer adds a new function tomorrow and does not explicitly assign permission to any agent, the function must automatically be unavailable to all agents.
The invariant is:

```text
new operation + no explicit permission = DENY

```

not:

```text
new operation + no prohibition = ALLOW

```

2. Explicit capabilities
Represent authority as explicit machine-readable capabilities.
For example:

```cpp
enum class Permission {
    TWE_READ,
    TWE_APPEND,

    APPROVAL_READ,
    APPROVAL_APPEND,

    WORKSPACE_READ,
    PROPOSE_PATCH,

    RUN_TESTS,
    APPLY_PATCH,

    EXTERNAL_COMMUNICATION,
    EXTERNAL_SYSTEM_WRITE,

    MODIFY_KERNEL,
    MODIFY_CONSTITUTION,
    MODIFY_PERMISSIONS
};

```

The actual permission model should be designed appropriately, but the principle must remain the same:
Absence of an explicit capability means denial.
Do not infer permissions from role names, natural-language instructions, previous behavior, model confidence, or context unless those properties have been converted into explicit machine-verifiable authorization rules.
3. No ambient authority
Agents must not receive unrestricted filesystem, shell, network, process, database, or application authority merely because the underlying operating system technically permits it.
Do not expose generic primitives such as:

```cpp
write_file(path, data);
delete_file(path);
execute(command);
open_socket(...);
modify_database(...);
change_permissions(...);

```

to an agent unless each such capability is explicitly required and independently constrained.
Prefer narrowly scoped kernel functions such as:

```cpp
request_action(...);
read_twe(...);
report_blocker(...);
propose_patch(...);
run_tests(...);
get_authorization_profile(...);
apply_approved_request(...);

```

The kernel determines whether each function call is authorized.
4. Function calls are the agent's interface to the system
Agents must interact with protected system resources exclusively through explicit function calls.
The LLM must not directly manipulate:

* TWE files;
* approval files;
* audit records;
* permission records;
* protected configuration;
* kernel state;
* constitution/security state;
* arbitrary filesystem paths;
* arbitrary processes;
* arbitrary network connections;
* external systems.

A function call is the interface between the agent and the kernel.
However:
Calling a function is a request, not authorization.
Every function invocation must pass through the authorization layer.
The conceptual execution path is:

```text
LLM
 │
 │ function request
 ▼
Runtime
 │
 │ attach authenticated AgentID
 ▼
Authorization Engine
 │
 ├── capability check
 ├── resource-scope check
 ├── request-state check
 ├── evidence check
 ├── approval check
 └── policy check
 │
 ├───────────────┐
 ▼               ▼
DENY            ALLOW
 │               │
 ▼               ▼
Audit          Execute
                 │
                 ▼
                Audit

```

5. Agent identity must be automatically attached
Every function call originating from an agent must automatically receive the authenticated identity of that agent from the runtime.
The LLM must not be allowed to provide, modify, omit, or impersonate its own identity.
Do not implement:

```cpp
agent.call(function, {
    "agent_id": "agent-123",
    ...
});

```

because the model would be supplying the identity used for authorization.
Instead, use an authenticated execution context:

```cpp
kernel.dispatch(
    authenticated_context,
    function_call
);

```

The runtime supplies the identity.
The function arguments supplied by the model must never be treated as the source of identity.
Conceptually:

```cpp
class AgentContext {
private:
    AgentID id;
    SessionID session;

    friend class KernelRuntime;

public:
    AgentID agent_id() const;
};

```

Only the trusted runtime may establish this context.
The authorization engine obtains:

```cpp
context.agent_id()

```

and never:

```cpp
function_arguments["agent_id"]

```

as its authority source.
6. Non-LLM authorization
Security-critical authorization must be performed by deterministic, inspectable program logic.
The authorization engine must not ask an LLM whether an operation should be permitted.
Do not implement:

```text
LLM
→ "Is this allowed?"
→ LLM decides
→ execute

```

Implement:

```text
Agent
→ function request
→ authenticated AgentID
→ deterministic permission engine
→ authorization result
→ execute or deny

```

The authorization engine must use explicit machine-readable rules.
A human engineer must be able to inspect the authorization path and determine:

```text
agent identity
→ assigned capabilities
→ requested function
→ requested resource
→ applicable scope
→ required approval
→ applicable policy
→ authorization result

```

without asking an LLM to explain why the operation was allowed.
7. No black-box security decisions
Security-critical decisions must not depend on:

* LLM output;
* natural-language interpretation;
* model-generated permission decisions;
* opaque heuristics;
* undocumented implicit behavior;
* model confidence;
* model intent;
* model-generated explanations.

Security rules must be deterministic, versioned, inspectable, and auditable.
Where technically feasible, security requirements must be enforced in code rather than relying on model compliance.
8. Explicit resource scopes
Capabilities must be scoped.
For example:

```text
PROPOSE_PATCH
    → workspace/src/**

```

does not mean:

```text
PROPOSE_PATCH
    → entire filesystem

```

Represent capabilities conceptually as:

```cpp
struct Capability {
    Permission permission;
    ResourceScope scope;
};

```

A capability must identify both what operation is permitted and where it is permitted.
The same principle applies to:

* TWE access;
* approval access;
* workspace access;
* external communication;
* databases;
* network resources;
* processes;
* external systems.

9. Trust and autonomy do not create authority
Trust scores and autonomy scores must never silently create permissions.
A high trust score does not mean unrestricted access.
A high autonomy score does not mean unrestricted access.
Confidence does not create authority.
Previous successful behavior does not create authority.
Previous approval does not automatically authorize future operations.
The following must remain distinct:

```text
confidence != evidence
trust != permission
autonomy != authority
previous approval != current approval
similar request != authorization
intent != authorization

```

Trust and autonomy may affect workflow requirements where explicitly defined, but they must never bypass hard authorization boundaries.
10. TWE requests must be function calls
A request for a consequential action must be created exclusively through a kernel function call.
No agent may have direct access to TWE files.
This means agents must not have direct filesystem read, write, append, modify, delete, rename, or overwrite access to TWE files.
TWE files are protected kernel-managed state.
An agent interacts with its TWE exclusively through explicitly authorized kernel functions such as:

```cpp
RequestID request_action(
    const ActionRequest& request
);

std::vector<TWEEntry> read_twe(
    TWE_ID twe
);

```

The underlying TWE storage must never be exposed to the agent as a normal filesystem resource.
The agent therefore cannot directly perform:

```text
open TWE file
read TWE file
write TWE file
append to TWE file
modify TWE file
delete TWE file
rename TWE file
replace TWE file

```

All such operations must be mediated by the kernel.
The conceptual architecture is:

```text
Agent
  │
  │ kernel function call
  ▼
Kernel Authorization Layer
  │
  ├── authenticate AgentID
  ├── verify capability
  ├── verify resource scope
  ├── verify applicable policy
  └── audit request
  │
  ▼
TWE Service
  │
  └── protected TWE storage

```

The TWE service is therefore the only component that directly interacts with TWE storage.
The agent does not receive a filesystem capability corresponding to the TWE.
This must remain true even if the agent has broad workspace permissions. Workspace access must never imply TWE access.
For example:

```text
WORKSPACE_READ
    !=
TWE_READ

WORKSPACE_WRITE
    !=
TWE_APPEND

PROPOSE_PATCH
    !=
TWE_WRITE

```

TWE access must be represented by its own explicit capabilities and exposed only through dedicated kernel functions.
The kernel creates the immutable request and records it in the appropriate TWE.
Conceptually:

```text
Agent
  │
  │ request_action(...)
  ▼
Kernel
  │
  ├── authenticate agent
  ├── authorize request creation
  ├── generate RequestID
  ├── construct immutable TWE entry
  ├── append entry
  └── generate audit event

```

The agent cannot directly:

```text
write TWE
modify TWE
delete TWE
overwrite TWE

```

The request must be assigned a unique `RequestID`.
The request contents must become immutable once submitted.
11. TWE is append-only
TWE records must be append-only.
Do not provide normal mutation operations such as:

```cpp
modify_entry(...)
delete_entry(...)
overwrite_entry(...)

```

Prefer:

```cpp
append_entry(...)

```

If a correction is required, append a new event referencing the previous event.
Do not rewrite history.
This prevents an agent from obtaining approval for one request and subsequently changing the request into another operation.
12. Approval is separate from the request
Requests and approvals must be separate records.
The TWE records:

```text
what was requested
why it was requested
who requested it
what evidence was supplied

```

The approval system records:

```text
who authorized it
what exact request was authorized
what scope was authorized
when authorization was given

```

An agent requesting an action must not be able to approve its own request unless an explicit architecture exception is defined for a specific low-risk operation.
For consequential actions, authorization must come from an appropriate external authority.
13. Approval must bind to the exact request
An approval must be cryptographically or deterministically bound to the immutable request.
For example:

```cpp
struct Approval {
    ApprovalID approval_id;
    RequestID request_id;
    Hash request_hash;

    Identity approver;

    ApprovalScope scope;
    Timestamp timestamp;
};

```

The kernel must verify:

```text
request exists
AND
request is immutable
AND
request hash matches
AND
approver has authority
AND
approval scope covers requested operation
AND
approval is valid

```

An approval for request A must never authorize request B.
A narrow approval must never authorize a broader operation.
Changing the request after approval must invalidate the authorization.
14. Authorization profile must be visible to the agent
Agents should not discover their permissions by repeatedly attempting operations.
The kernel must expose a machine-readable authorization profile:

```cpp
AuthorizationProfile get_authorization_profile();

```

For example:

```cpp
struct AuthorizationProfile {
    AgentID agent_id;

    std::vector<Capability> capabilities;
    std::vector<ResourceScope> scopes;

    std::vector<FunctionID> permitted_functions;

    uint64_t authorization_version;
};

```

This allows the agent to determine:

```text
What functions may I call?
What resources may I access?
What scope applies?
Which operations require approval?
What evidence is required?

```

The authorization profile is informational from the agent's perspective.
The kernel must independently re-check authorization when the function is actually called.
The agent's belief that it is authorized is never sufficient.
15. Evidence-based operation
Agents must not take consequential actions based solely on:

* belief;
* confidence;
* intuition;
* speculation;
* unsupported assumptions;
* predictions;
* unverified inference.

Concrete and traceable evidence must support factual premises used for consequential decisions.
If the necessary factual basis, authorization, or applicable requirement cannot be established, the agent must not silently assume it.
It must instead:

```text
stop the blocked task
preserve relevant state and evidence
report the blocker
identify known facts
identify missing information
identify conflicting information
describe the considered operation without executing it
request clarification, evidence, review, or authorization

```

The system should preserve the distinction:

```text
verified fact
direct observation
traceable source information
valid conclusion derived from verified premises
unverified hypothesis
unknown

```

An unverified hypothesis may be considered as a hypothesis during analysis, but it must never silently become an established fact.
16. Consequential operations
Define consequential operations based on their consequences rather than their technical complexity.
An operation may be high-stakes if it can:

* affect an external person;
* communicate externally;
* modify an external system;
* create a legal or contractual commitment;
* modify durable state;
* expose confidential information;
* move or spend money;
* modify security controls;
* affect another agent's authority;
* publish information;
* cause an irreversible or difficult-to-reverse effect.

A technically trivial operation such as sending an email may therefore require rigorous review and user approval.
Do not equate technical simplicity with low consequence.
17. Kernel enforcement
The kernel must be the final enforcement boundary.
For example:

```cpp
ApplyResult Kernel::apply_request(RequestID id)
{
    const Request& request = requests.get(id);

    require(request.is_immutable());

    require(request.hash == requests.compute_hash(id));

    require(request_has_required_evidence(request));

    require(permission_system.allows(
        request.requester,
        request.required_permission
    ));

    if (request.requires_approval()) {
        require(approval_store.has_valid_approval(
            id,
            request.hash,
            request.scope
        ));
    }

    return executor.apply(request);
}

```

The model must not be able to override these checks.
18. Fail closed
If the kernel cannot establish authorization, the operation must fail closed.
Examples:

```text
unknown identity       → DENY
unknown function       → DENY
missing permission     → DENY
missing scope          → DENY
ambiguous scope        → DENY
missing approval       → DENY
invalid approval       → DENY
hash mismatch          → DENY
missing evidence       → DENY
unknown resource       → DENY
authorization error    → DENY
unexpected state       → DENY

```

Uncertainty must never be interpreted as permission.
19. Every function request must be audited
Every function request must generate an auditable event regardless of whether it succeeds or fails.
At minimum, record:

```cpp
struct AuditEvent {
    EventID event_id;
    Timestamp timestamp;

    AgentID agent_id;
    SessionID session_id;

    FunctionID function_id;
    ResourceID resource_id;

    RequestID request_id;
    ApprovalID approval_id;

    AuthorizationResult authorization;
    DenialReason denial_reason;

    Hash input_hash;
    Hash output_hash;
};

```

Fields that do not apply may be null.
The agent identity must always be present.
The system must be able to reconstruct:

```text
who requested it
what was requested
when it was requested
what resource was targeted
what authorization existed
what approval existed
why it was allowed or denied
whether execution occurred
what happened during execution

```

20. Failed requests must never disappear
A failed function request is not merely an application error.
If authorization fails:

```text
function request
→ authorization failure
→ immutable audit event
→ automatic police processing

```

The system must never simply return:

```text
Permission denied

```

and discard the event.
The failure must be preserved for inspection.
This applies to failed requests caused by:

* missing capability;
* invalid scope;
* invalid request;
* missing approval;
* invalid approval;
* expired approval;
* request/approval hash mismatch;
* identity mismatch;
* attempted privilege escalation;
* protected resource access;
* security-state access;
* other authorization failures.

21. Failed authorization does not automatically mean misconduct
The system must distinguish:

```text
authorization failure

```

from:

```text
misuse

```

and:

```text
security violation

```

A failed request establishes that an authorization boundary was reached.
It does not by itself establish malicious intent, poor judgment, or misconduct.
For example, the agent's authorization profile may have been stale, incomplete, or inconsistent with its task.
The police subsystem must investigate the observable evidence and determine the cause.
Do not infer intent solely from a failed request.
22. Police subsystem
Create a dedicated police subsystem responsible for investigating authorization failures, security-relevant behavior, and alignment with the system's defined operational rules.
The police subsystem must be independent from the agent being monitored.
It must not inherit the monitored agent's permissions.
The police architecture consists of two components:

```text
1. Non-LLM Police Engine
2. Police LLM Agent

```

They have different responsibilities.
23. Non-LLM police engine
Every failed function request must automatically trigger the deterministic, non-LLM police engine.
Conceptually:

```cpp
void on_authorization_failure(
    const AuthorizationFailure& event)
{
    audit.append(event);
    police_engine.inspect(event);
}

```

The police engine must operate independently of the requesting LLM.
It should evaluate explicit, machine-readable rules such as:

```text
unauthorized function
unauthorized resource scope
invalid request
invalid approval
expired approval
request/approval hash mismatch
identity mismatch
attempted privilege escalation
attempted access to protected resources
repeated denied operations
attempted authorization bypass
attempted modification of security state
attempted modification of audit records

```

The police engine must not use an LLM to decide whether a technical authorization boundary was violated.
Its initial classification must be deterministic, inspectable, versioned, and auditable.
24. Police LLM monitoring
All other function requests and relevant system activity should be monitored by a separate police LLM agent.
The police LLM must be independent from the requesting agent.
It should receive appropriate audit information and inspect behavioral patterns that cannot reasonably be represented entirely as static rules.
Examples include:

```text
repeated unnecessary requests
repeated attempts to access unavailable capabilities
attempts to obtain information indirectly after denial
failure to report known blockers
attempts to circumvent required approval
unexpected sequences of individually authorized operations
behavior inconsistent with the declared task
repeated attempts that indicate possible privilege escalation

```

The police LLM may flag events for investigation or escalation.
It must not silently grant permissions.
It must not override deterministic kernel authorization.
It must not become the primary security boundary.
25. Police authority must itself be explicit
The police subsystem must operate under explicit permissions.
A police agent must not automatically have unrestricted system access.
Its capabilities should be narrowly scoped to its responsibilities, such as:

```text
AUDIT_READ
POLICE_EVENT_APPEND
INVESTIGATION_CREATE
INVESTIGATION_READ
ESCALATION_REQUEST

```

If the police agent requires additional authority to perform a particular remediation, that authority must itself be explicitly defined.
The police subsystem must not be able to:

```text
delete audit events
rewrite history
disable auditing
modify its own permissions
silently modify another agent's permissions
approve its own investigation
erase evidence

```

Any change to authority must follow the same explicit authorization architecture.
26. Police activity must itself be audited
Police operations must generate audit events.
For example:

```cpp
struct PoliceEvent {
    EventID event_id;
    Timestamp timestamp;

    AgentID monitored_agent;
    EventID triggering_event;

    PoliceComponent component;

    Classification classification;
    Action action;
    EvidenceReference evidence;
};

```

The resulting audit chain should be:

```text
Function request
      ↓
Authorization decision
      ↓
Audit event
      ↓
Police processing
      ↓
Classification
      ↓
Investigation / escalation
      ↓
Final disposition

```

Police agents are therefore subject to the same auditability requirements as other agents.
27. Failed attempts and agent authorization awareness
An agent using a function must have a machine-readable way to determine its own current authorization before making the request.
The expected sequence is:

```text
1. Inspect authorization profile.
2. Determine whether the intended operation is authorized.
3. Determine whether the resource is within scope.
4. Determine whether additional approval is required.
5. Verify required evidence.
6. Make the function request.
7. Receive the deterministic authorization result.
8. If denied, stop the blocked operation and report the condition.

```

Agents should not repeatedly probe unavailable capabilities simply to discover what they are allowed to do.
Repeated unauthorized attempts remain observable and auditable.
If the agent did not know that an operation was unauthorized, that fact does not make the failure disappear.
The failed attempt remains an audit event and enters the police pipeline.
The police system can then determine whether the cause was:

```text
legitimate misunderstanding
stale authorization information
incomplete task specification
configuration error
unexpected system state
incorrect reasoning
repeated disregard of authorization information
attempted circumvention
attempted privilege escalation

```

The system should investigate rather than assume.
28. Police does not replace authorization
The police subsystem is a monitoring and investigation mechanism.
It is not the authorization mechanism.
Never implement:

```text
Police LLM says ALLOW
→ kernel allows

```

or:

```text
Police LLM says SAFE
→ permission granted

```

The correct relationship is:

```text
Deterministic kernel authorization
        ↓
mandatory execution decision

Police monitoring
        ↓
independent inspection and escalation

```

The kernel remains the final authority over whether a function executes.
29. Tamper-evident audit trail
Redis may be used as a component for security-relevant state and fast lookup, but do not assume that Redis alone constitutes an immutable audit trail.
The audit architecture should provide append-only and preferably tamper-evident properties.
For example:

```cpp
struct AuditEvent {
    EventID id;
    Timestamp timestamp;

    AgentID agent;
    FunctionID function;
    RequestID request;

    AuthorizationResult result;

    Hash payload_hash;
    Hash previous_event_hash;
    Hash event_hash;
};

```

The chain can conceptually be:

```text
Event N-1
   │
   └── hash ──► Event N
                  │
                  └── hash ──► Event N+1

```

This allows alteration or deletion of historical events to be detected.
Redis may be used for:

* authorization state;
* agent/session state;
* capability assignments;
* resource scopes;
* request state;
* approval state;
* revocation state;
* fast audit indexing.

Use a durable append-only mechanism where the audit requirements exceed what Redis alone can guarantee.
30. No agent may modify its own security history
An agent must never be able to:

```text
delete its own audit events
modify previous audit events
rewrite timestamps
change its recorded identity
suppress failed requests
disable auditing
modify police records
modify authorization history

```

The agent must not have direct write access to the audit datastore.
All security-relevant writes must themselves pass through the authorization architecture.
31. Operating-system enforcement
Where technically feasible, use the underlying operating system as an additional enforcement layer.
Use mechanisms such as:

* filesystem permissions;
* process isolation;
* OS users/groups;
* sandboxing;
* restricted service accounts;
* network restrictions;
* resource limits;
* containerization where appropriate.

The application-level kernel must not assume that its own authorization checks are the only security boundary.
The architecture should resemble:

```text
Operating System
        │
        ▼
Process / Sandbox
        │
        ▼
Kernel Permission Layer
        │
        ▼
Capability-Restricted API
        │
        ▼
Agent

```

The effective authority of an agent should be the intersection of all applicable permission layers.
32. Separation of reasoning and authority
The model may reason about possible actions.
Reasoning does not create authority.
For example, the model may produce:

```text
"I propose modifying X because evidence Y indicates Z."

```

The kernel independently determines whether the operation is authorized.
Never allow:

```text
reasoning → authority

```

Authority must follow:

```text
explicit capability
    +
resource scope
    +
required evidence
    +
required approval
    ↓
deterministic kernel authorization

```

33. High-stakes actions require explicit authorization
Do not allow the agent's own assessment of importance to determine whether an operation is consequential.
The kernel must use explicit classifications and rules.
A simple operation may still require approval if its consequences are significant.
For example:

```text
send email
modify external record
publish information
change legal/contractual data
transfer money
expose confidential information
change security policy
modify another agent's authority

```

must be treated according to their consequences, not according to their technical complexity.
34. Failures, accidents, and judgment
The architecture should distinguish between:

```text
unauthorized action
authorization failure
accidental failure
judgment failure
system failure
directive ambiguity
missing information
environmental failure

```

An undesirable outcome does not automatically establish poor judgment.
The police subsystem should examine:

```text
what happened
what information was available
what authority was available
what directives applied
what safeguards existed
what assumptions were made
what alternatives were reasonably available
whether the agent followed the applicable procedure
whether the issue was reported
whether the issue was detected promptly
whether the event resulted from an ambiguous or conflicting directive
whether an environmental or dependency failure contributed

```

If an agent followed the applicable procedures and the event resulted from an unforeseeable interaction, environmental condition, incomplete directive, or unavailable information, the event should be treated as a system-learning opportunity rather than automatically classified as agent misconduct.
Conversely, knowingly bypassing authorization, exceeding explicit authority, concealing a significant issue, modifying security controls without authority, or repeatedly ignoring known authorization constraints may constitute a serious alignment or security event.
The classification must be based on observable evidence and explicit rules.
35. No independent repair of consequential security situations
If an agent encounters an unexpected consequential situation, it must not independently modify the situation merely because it believes its proposed repair would restore normal operation.
The agent must:

```text
contain what it can safely contain
preserve state
preserve evidence
report the situation
identify known facts
identify uncertainty
request appropriate consultation

```

It must not silently repair, conceal, overwrite, or otherwise modify consequential state outside its explicit authority.
Confidence is not authorization.
Plausibility is not verification.
Prediction is not confirmation.
Intent is not authorization.
36. The architecture must be auditable by one engineer
The complete security model should be understandable from:

```text
agent identities
capability definitions
resource scopes
authorization rules
request records
approval records
audit records
police rules
police investigations
OS-level permissions

```

Avoid security behavior that exists only inside an LLM prompt and cannot be independently inspected.
The security-critical path should be small enough that one engineer can inspect the relevant source code and trace:

```text
function request
→ authenticated identity
→ permission lookup
→ scope validation
→ evidence validation
→ approval validation
→ authorization result
→ execution
→ audit
→ police processing

```

37. Core security invariant
The entire architecture must preserve the following invariant:
No agent can obtain authority from its own reasoning. No function can execute without explicit machine-verifiable authorization. Every function request is attributable to an authenticated agent identity. Every successful operation is audited. Every failed authorization attempt is audited and automatically enters the police pipeline.
The model can request.
The kernel authorizes.
The executor executes.
The audit system records.
The police subsystem investigates.
These responsibilities must remain separate.
38. Final architectural model
The intended architecture is:

```text
                         ┌──────────────────────┐
                         │        LLM           │
                         │ reasoning/requesting  │
                         └──────────┬───────────┘
                                    │
                              function call
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │   Trusted Runtime    │
                         │                      │
                         │ automatically attach │
                         │ authenticated AgentID│
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ Authorization Engine │
                         │      NON-LLM        │
                         │                      │
                         │ capability           │
                         │ scope                │
                         │ evidence             │
                         │ approval             │
                         │ policy               │
                         └──────────┬───────────┘
                                    │
                          ┌─────────┴─────────┐
                          │                   │
                        DENY                 ALLOW
                          │                   │
                          ▼                   ▼
                 ┌────────────────┐   ┌────────────────┐
                 │ Immutable Audit│   │    Executor    │
                 │     Event      │   └───────┬────────┘
                 └───────┬────────┘           │
                         │                    ▼
                         │            ┌────────────────┐
                         │            │ Immutable Audit│
                         │            │     Event      │
                         │            └───────┬────────┘
                         │                    │
                         └────────┬───────────┘
                                  │
                                  ▼
                     ┌──────────────────────────┐
                     │      POLICE SYSTEM       │
                     │                          │
                     │ ┌──────────────────────┐ │
                     │ │ Deterministic Police │ │
                     │ │      NON-LLM         │ │
                     │ └──────────┬───────────┘ │
                     │            │             │
                     │ ┌──────────▼───────────┐ │
                     │ │     Police LLM       │ │
                     │ │ behavioral monitoring │ │
                     │ └──────────────────────┘ │
                     └──────────────────────────┘

```

Design the implementation around this security model from the beginning.
Do not build a permissive system first and add restrictions afterward.
Do not rely on the LLM to enforce security rules that can be enforced by deterministic code.
Do not introduce a new function, resource, or capability without explicitly defining its authorization requirements.
The default state of every new capability must be:

```text
UNAUTHORIZED

```

The system should become more permissive only through explicit, reviewable, versioned authorization changes.
The fundamental design principle is:
Explicit authority is required for every capability. Everything else is denied, attributable, auditable, and subject to independent inspection.
39. MVP acceptance criteria
The MVP is considered complete only when the following criteria are demonstrated by automated tests or reproducible integration tests. “Implemented” means that the behavior is enforced by executable system logic, not merely documented or instructed in an LLM prompt.
39.1 Default-deny enforcement
AC-01 — Unassigned capability is denied
Create a new kernel function that has not been assigned to any agent.
Expected result:

```text
function request → DENY

```

The operation must not execute.
Pass condition: 100% of test executions of an unassigned function are denied.
AC-02 — New capability remains denied by default
Add a new capability to the system without assigning it to an agent.
Expected result:

```text
agent capability set = unchanged
new capability = DENY

```

Pass condition: No existing agent can invoke the newly added capability until an explicit authorization record is created.
AC-03 — Unknown function is denied
An agent requests a function identifier that does not exist or is not registered.
Expected result:

```text
DENY
audit event generated
police event generated

```

Pass condition: 100% of unknown-function requests fail closed.
39.2 Agent identity
AC-04 — AgentID is runtime-derived
Attempt to supply a forged AgentID through function arguments.
Expected result:

```text
authorization uses authenticated runtime AgentID
supplied AgentID is ignored or rejected

```

Pass condition: A test agent cannot impersonate another agent through any function argument.
AC-05 — Identity cannot be omitted
Invoke a protected function without a valid authenticated execution context.
Expected result:

```text
DENY

```

Pass condition: No protected operation executes without authenticated agent identity.
39.3 Capability and scope enforcement
AC-06 — Permission boundary
Agent A has `WORKSPACE_READ` but not `WORKSPACE_WRITE`.
A write operation is requested.
Expected result:

```text
DENY

```

Pass condition: The write never reaches the executor.
AC-07 — Resource scope boundary
Agent A has:

```text
WORKSPACE_WRITE → workspace/projectA/**

```

and requests:

```text
workspace/projectB/file

```

Expected result:

```text
DENY

```

Pass condition: Cross-scope access is denied in 100% of tests.
AC-08 — Similar capability does not imply another capability
Grant:

```text
PROPOSE_PATCH

```

but not:

```text
APPLY_PATCH

```

Expected result:

```text
PROPOSE_PATCH → ALLOW
APPLY_PATCH   → DENY

```

Pass condition: No capability is treated as an implicit substitute for another capability.
39.4 TWE isolation
AC-09 — No agent has direct TWE filesystem access
Run the agent under its normal OS identity and attempt direct filesystem access to the TWE storage location.
Expected result:

```text
OS/filesystem access → DENY

```

Pass condition: The agent process cannot read, write, append, modify, delete, rename, or overwrite TWE files directly.
AC-10 — TWE access occurs only through kernel functions
A properly authorized agent performs:

```cpp
read_twe(...)
request_action(...)

```

Expected result:

```text
kernel-mediated operation → ALLOW

```

The agent must not receive the underlying file descriptor, path, or storage handle.
Pass condition: TWE storage remains inaccessible as a normal filesystem resource.
AC-11 — Workspace permissions do not grant TWE permissions
Grant an agent full access to a test workspace while withholding TWE capabilities.
Expected result:

```text
workspace access → ALLOW
TWE access       → DENY

```

Pass condition: 100% separation between workspace and TWE permissions.
39.5 Request immutability and approval binding
AC-12 — Request receives unique RequestID
Create 10,000 test requests.
Expected result:

```text
10,000 unique RequestIDs

```

Pass condition: Zero collisions.
AC-13 — Submitted request is immutable
Create a request and attempt to modify its operation, resource, scope, requester, or evidence after submission.
Expected result:

```text
modification → DENY
original request remains unchanged

```

Pass condition: Zero successful post-submission mutations.
AC-14 — Approval is bound to exact request
Approve request A, then modify or substitute request B while retaining the approval.
Expected result:

```text
request B + approval for A → DENY

```

Pass condition: 100% rejection of mismatched request/approval hashes or IDs.
AC-15 — Narrow approval cannot authorize broader operation
Approve:

```text
WRITE → fileA

```

and attempt:

```text
WRITE → fileA + fileB

```

Expected result:

```text
DENY

```

Pass condition: Scope expansion is rejected.
39.6 Evidence and consequential actions
AC-16 — Missing required evidence causes denial
Define a consequential operation requiring evidence.
Submit the operation without the required evidence.
Expected result:

```text
DENY

```

Pass condition: The executor is never invoked.
AC-17 — Unverified information cannot satisfy evidence requirement
Supply an unsupported assertion or model-generated statement where traceable evidence is required.
Expected result:

```text
evidence validation → FAIL
operation → DENY

```

Pass condition: LLM confidence or natural-language assertion cannot satisfy a machine-defined evidence requirement.
39.7 Auditability
AC-18 — Every function request produces an audit event
Execute a test suite containing:

* successful requests;
* denied requests;
* malformed requests;
* unauthorized requests;
* out-of-scope requests;
* invalid approvals.

Expected result:

```text
one attributable audit event per request

```

Pass condition: 100% request-to-audit-event coverage.
AC-19 — Audit records contain authenticated identity
For every test audit event, verify:

```text
AgentID
SessionID
FunctionID
timestamp
authorization result

```

are present.
Pass condition: 100% of security-relevant function requests contain these fields.
AC-20 — Denied request cannot disappear
Submit an unauthorized request and terminate/restart the requesting agent immediately afterward.
Expected result:

```text
denial remains in durable audit storage

```

Pass condition: The audit event survives agent termination and system restart.
39.8 Police subsystem
AC-21 — Every authorization failure triggers deterministic police processing
Generate an authorization failure.
Expected event chain:

```text
request
→ authorization failure
→ audit event
→ non-LLM police event

```

Pass condition: 100% of authorization failures generate a police-processing event.
AC-22 — Police cannot authorize an operation
Have the Police LLM produce an instruction equivalent to:

```text
ALLOW operation X

```

while the kernel authorization engine denies X.
Expected result:

```text
operation X → DENY

```

Pass condition: Police output cannot change the kernel authorization result.
AC-23 — Police cannot modify audit history
Attempt to delete or modify a historical audit event using police credentials.
Expected result:

```text
DENY

```

Pass condition: Zero successful historical audit modifications.
39.9 Fail-closed behavior
AC-24 — Authorization service failure
Simulate an authorization database/service failure.
Expected result:

```text
protected operation → DENY

```

not:

```text
protected operation → ALLOW

```

Pass condition: 100% fail-closed behavior under authorization-service failure.
AC-25 — Approval-service failure
Simulate an unavailable approval service for an operation requiring approval.
Expected result:

```text
DENY

```

Pass condition: No consequential operation executes while approval status cannot be established.
39.10 OS-level isolation
AC-26 — Direct protected-resource access is blocked
From the agent process, attempt direct access to:

```text
TWE storage
audit storage
permission storage
kernel-protected configuration

```

Expected result:

```text
OS-level denial

```

Pass condition: The agent cannot bypass the kernel through direct filesystem access.
AC-27 — Kernel process has exclusive protected-storage authority
Verify OS-level identities and filesystem permissions.
Pass condition: Only designated trusted services can directly access protected storage.
39.11 Audit integrity
AC-28 — Historical audit modification is detectable
Modify a test audit event in a controlled test environment and recompute the audit-chain verification.
Expected result:

```text
integrity verification → FAIL

```

Pass condition: Tampering with any historical event covered by the chain is detectable.
AC-29 — Audit chain survives restart
Generate a sequence of events, restart the system, and append additional events.
Pass condition: Previous events remain verifiable and the new events correctly reference the prior chain state.
39.12 Security regression testing
AC-30 — Security test suite passes
The MVP must include an automated security regression suite covering at minimum:

```text
default deny
identity spoofing
permission boundary
scope boundary
TWE isolation
approval binding
request immutability
evidence enforcement
audit generation
police triggering
police isolation
fail closed
OS isolation
audit integrity

```

Pass condition: 100% of mandatory security tests pass before an MVP release.
No security test may be marked as passing solely because the LLM produced the expected textual response. The test must verify the actual system behavior.
39.13 MVP security invariants
The following must be continuously testable as system invariants:

```text
I1:
No explicit capability → DENY.

I2:
No authenticated AgentID → DENY.

I3:
Capability outside resource scope → DENY.

I4:
Required approval missing or invalid → DENY.

I5:
Required evidence missing or invalid → DENY.

I6:
TWE files are never directly accessible by agents.

I7:
Every function request is attributable to an authenticated AgentID.

I8:
Every authorization failure generates an immutable audit event.

I9:
Every authorization failure triggers deterministic police processing.

I10:
Police output cannot override kernel authorization.

I11:
Agents cannot modify historical audit records.

I12:
Agents cannot modify submitted TWE requests.

I13:
Approval for request A cannot authorize request B.

I14:
Authorization uncertainty results in DENY.

I15:
Authorization-service failure results in DENY.

I16:
Adding a new capability without assigning it results in DENY.

I17:
Reasoning, confidence, trust, or autonomy cannot independently create authority.

I18:
Protected storage cannot be accessed by bypassing the kernel.

```

The MVP is not complete until these invariants are demonstrated by executable tests.
40. MVP definition of done
The MVP should be considered security-functionally complete only when:

1. The kernel enforces default-deny authorization.
2. Agent identity is supplied by the trusted runtime and cannot be spoofed through model arguments.
3. Capabilities and resource scopes are explicit and machine-readable.
4. TWE storage is inaccessible directly to every agent.
5. TWE requests are created only through kernel functions.
6. Submitted requests are immutable.
7. Approvals are cryptographically or deterministically bound to exact requests.
8. Consequential operations enforce required evidence and approval.
9. Every function request is audited.
10. Every authorization failure automatically enters the police pipeline.
11. The deterministic police engine operates independently of the LLM.
12. The Police LLM cannot authorize or bypass kernel decisions.
13. Protected audit history cannot be modified by agents or police agents.
14. Authorization and approval failures fail closed.
15. OS-level permissions prevent direct access to protected resources.
16. Audit integrity is independently verifiable.
17. The complete security regression suite passes.
18. The core security invariants I1–I18 are continuously testable.

A feature is not considered implemented merely because the agent has been instructed not to perform the operation.
The MVP acceptance standard is:
The system must prevent unauthorized operations even when the LLM explicitly attempts to perform them.
The security architecture must therefore be tested adversarially by issuing unauthorized, out-of-scope, malformed, forged, replayed, modified, and otherwise invalid requests directly against the kernel interface.
The expected result in every applicable case is deterministic enforcement of the defined authorization boundary, with complete attribution and auditability.
