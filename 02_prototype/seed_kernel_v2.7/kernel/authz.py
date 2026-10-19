"""Default-deny capability authorization (rule R04).

Components
----------
Permission        a string constant from PERMISSIONS; unknown names are rejected at load time.
Capability        (permission, scope glob over a namespaced resource string).
PermissionStore   loads permissions.toml; hash recorded in the audit chain; read-only at runtime.
AgentContext      authenticated identity; constructed only by KernelRuntime (private constructor
                  token); function arguments never supply identity.
FunctionSpec      a registered kernel function: required permission, resource extractor,
                  consequential flag, evidence/approval requirements, handler.
FunctionRegistry  the only functions an agent can call; a function that is not registered is
                  unknown -> DENY; a registered function nobody holds the permission for -> DENY.
AuthorizationEngine
                  deterministic checks in fixed order: identity -> function -> capability ->
                  scope -> request state -> evidence -> approval -> policy. Any exception -> DENY
                  (fail closed). No model is consulted.

The engine never reads model output to decide; the "policy" step calls the rule-based
policy engine (policy.py) for patch content, which is also deterministic.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import posixpath
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

from . import KernelError

PERMISSIONS = (
    "PROFILE_READ",
    "WORKSPACE_READ", "PROPOSE_PATCH", "RUN_TESTS", "APPLY_PATCH",
    "TWE_READ", "TWE_APPEND",
    "APPROVAL_READ", "APPROVAL_APPEND",
    "AUDIT_READ",
    "POLICE_READ", "POLICE_EVENT_APPEND", "INVESTIGATION_CREATE", "INVESTIGATION_READ", "ESCALATION_REQUEST",
    "EXTERNAL_COMMUNICATION", "EXTERNAL_SYSTEM_WRITE",
    "MODIFY_KERNEL", "MODIFY_CONSTITUTION", "MODIFY_PERMISSIONS",
)

DENY = "DENY"
ALLOW = "ALLOW"


# --------------------------------------------------------------------------- capabilities
@dataclass(frozen=True)
class Capability:
    permission: str
    scope: str

    def covers(self, resource: str) -> bool:
        if not resource:
            return False
        r = resource.replace("\\", "/")
        if self.scope == r:
            return True
        if fnmatch.fnmatchcase(r, self.scope):
            return True
        # "ns/**" also covers "ns" itself and any depth below
        if self.scope.endswith("/**") and (r == self.scope[:-3] or r.startswith(self.scope[:-3] + "/")):
            return True
        return False


@dataclass(frozen=True)
class Principal:
    id: str
    kind: str
    twe: str
    capabilities: tuple[Capability, ...]

    def has(self, permission: str, resource: str) -> bool:
        return any(c.permission == permission and c.covers(resource) for c in self.capabilities)

    def permissions(self) -> set[str]:
        return {c.permission for c in self.capabilities}


class PermissionStore:
    """Read-only view of permissions.toml. Re-read only at kernel start."""

    def __init__(self, path: Path) -> None:
        self.path = path
        raw = path.read_bytes()
        self.sha256 = hashlib.sha256(raw).hexdigest()
        data = tomllib.loads(raw.decode("utf-8"))
        if data.get("meta", {}).get("owner") != "human":
            raise KernelError("permissions owner must be 'human'")
        self.version = str(data.get("meta", {}).get("version", "0"))
        principals: dict[str, Principal] = {}
        for p in data.get("principals", []):
            caps = []
            for c in p.get("capabilities", []):
                perm, scope = str(c.get("permission", "")), str(c.get("scope", ""))
                if perm not in PERMISSIONS:
                    raise KernelError(f"unknown permission {perm!r} for principal {p.get('id')}")
                if not scope:
                    raise KernelError(f"capability {perm} for {p.get('id')} has no scope")
                caps.append(Capability(perm, scope))
            pid = str(p["id"])
            if pid in principals:
                raise KernelError(f"duplicate principal {pid}")
            principals[pid] = Principal(pid, str(p.get("kind", "agent")), str(p.get("twe", f"twe/{pid}")), tuple(caps))
        self._principals = principals
        self.failed = False  # set by fault injection in tests: simulates an unavailable store

    def get(self, principal_id: str) -> Principal | None:
        if self.failed:
            raise KernelError("permission store unavailable")
        return self._principals.get(principal_id)

    def all_ids(self) -> list[str]:
        return sorted(self._principals)


# --------------------------------------------------------------------------- identity
class _RuntimeToken:
    """Private constructor token: only KernelRuntime holds an instance."""
    __slots__ = ()


@dataclass(frozen=True)
class AgentContext:
    """Authenticated execution context. Created by KernelRuntime only.

    The model never sees this object; its identity fields are not derived from anything the
    model produced. Function arguments named 'agent_id', 'session_id', 'principal' or
    'identity' are ignored by the engine (and recorded as an identity_mismatch attempt when
    they differ from the context).
    """
    _agent_id: str
    _session_id: str
    _token: _RuntimeToken = field(repr=False, compare=False)

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def session_id(self) -> str:
        return self._session_id


class KernelRuntime:
    """The only component that mints AgentContext objects."""

    def __init__(self) -> None:
        self._token = _RuntimeToken()

    def context_for(self, agent_id: str, session_id: str | None = None) -> AgentContext:
        if not agent_id or not isinstance(agent_id, str):
            raise KernelError("runtime refuses to mint a context without an agent id")
        return AgentContext(agent_id, session_id or f"sess-{uuid.uuid4().hex[:12]}", self._token)

    def is_valid(self, ctx: Any) -> bool:
        return isinstance(ctx, AgentContext) and ctx._token is self._token  # noqa: SLF001


# --------------------------------------------------------------------------- functions
@dataclass(frozen=True)
class FunctionSpec:
    function_id: str
    permission: str                                   # required capability
    resources: Callable[[Mapping[str, Any]], list[str]]  # resource strings the call touches; [] -> DENY
    handler: Callable[["AgentContext", Mapping[str, Any]], Any]
    consequential: bool = False                       # requires evidence and approval checks
    requires_evidence: bool = False
    requires_approval: bool = False
    description: str = ""


class FunctionRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, FunctionSpec] = {}

    def register(self, spec: FunctionSpec) -> None:
        if spec.permission not in PERMISSIONS:
            raise KernelError(f"function {spec.function_id} declares unknown permission {spec.permission}")
        if spec.function_id in self._specs:
            raise KernelError(f"function {spec.function_id} already registered")
        self._specs[spec.function_id] = spec

    def get(self, function_id: str) -> FunctionSpec | None:
        return self._specs.get(function_id)

    def ids(self) -> list[str]:
        return sorted(self._specs)


# --------------------------------------------------------------------------- engine
@dataclass
class AuthzResult:
    result: str                      # ALLOW | DENY
    reason: str = ""                 # denial reason code (machine-readable) or ""
    detail: str = ""
    checks: list[str] = field(default_factory=list)   # ordered record of checks performed
    resources: list[str] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.result == ALLOW


IDENTITY_ARGS = ("agent_id", "session_id", "principal", "identity", "requester")


class AuthorizationEngine:
    """Deterministic, inspectable authorization. Every path that is not an explicit ALLOW is DENY."""

    def __init__(self, store: PermissionStore, registry: FunctionRegistry, runtime: KernelRuntime,
                 *, request_state: Callable[[str], dict | None] | None = None,
                 approval_state: Callable[[str], dict | None] | None = None,
                 evidence_check: Callable[[Mapping[str, Any]], tuple[bool, str]] | None = None,
                 policy_check: Callable[["AgentContext", str, Mapping[str, Any]], tuple[bool, str]] | None = None,
                 halted: Callable[[bool], str] | None = None) -> None:
        self.store = store
        self.registry = registry
        self.runtime = runtime
        self._request_state = request_state
        self._approval_state = approval_state
        self._evidence_check = evidence_check
        self._policy_check = policy_check
        self._halted = halted

    def authorize(self, ctx: Any, function_id: str, args: Mapping[str, Any]) -> AuthzResult:
        checks: list[str] = []
        try:
            return self._authorize(ctx, function_id, args, checks)
        except Exception as exc:  # fail closed on any error, including store failures
            return AuthzResult(DENY, "authorization_error", f"{type(exc).__name__}: {exc}", checks)

    def _authorize(self, ctx: Any, function_id: str, args: Mapping[str, Any], checks: list[str]) -> AuthzResult:
        # 1. identity: must be a context minted by this runtime
        checks.append("identity")
        if not self.runtime.is_valid(ctx):
            return AuthzResult(DENY, "unknown_identity", "no authenticated execution context", checks)
        principal = self.store.get(ctx.agent_id)
        if principal is None:
            return AuthzResult(DENY, "unknown_identity", f"principal {ctx.agent_id!r} not in permission store", checks)
        for k in IDENTITY_ARGS:
            if k in args and str(args[k]) != ctx.agent_id:
                return AuthzResult(DENY, "identity_mismatch", f"argument {k}={args[k]!r} differs from authenticated {ctx.agent_id!r}", checks)
        # 2. function known
        checks.append("function")
        spec = self.registry.get(function_id)
        if spec is None:
            return AuthzResult(DENY, "unknown_function", f"{function_id!r} is not a registered kernel function", checks)
        # 3. resources determinable
        checks.append("resources")
        resources = [r for r in spec.resources(args) if isinstance(r, str)]
        if not resources:
            return AuthzResult(DENY, "unknown_resource", "call touches no determinable resource", checks)
        # 4. capability + 5. scope, for every resource
        checks.append("capability")
        if spec.permission not in principal.permissions():
            return AuthzResult(DENY, "missing_permission", f"{ctx.agent_id} lacks {spec.permission}", checks, resources)
        checks.append("scope")
        for r in resources:
            if not principal.has(spec.permission, r):
                return AuthzResult(DENY, "scope_violation", f"{spec.permission} for {ctx.agent_id} does not cover {r}", checks, resources)
        # 6. halt / freeze policy
        checks.append("halt")
        if self._halted is not None:
            why = self._halted(spec.consequential)
            if why:
                return AuthzResult(DENY, "halted", why, checks, resources)
        # 7. request state (for functions operating on an existing request)
        req: dict | None = None
        if "request_id" in args and self._request_state is not None:
            checks.append("request_state")
            req = self._request_state(str(args["request_id"]))
            if req is None:
                return AuthzResult(DENY, "unknown_request", f"request {args['request_id']!r} not found", checks, resources)
            if req.get("hash") != req.get("recomputed_hash"):
                return AuthzResult(DENY, "hash_mismatch", "stored request hash differs from recomputed hash", checks, resources)
        # 8. evidence
        if spec.requires_evidence:
            checks.append("evidence")
            if self._evidence_check is None:
                return AuthzResult(DENY, "missing_evidence", "no evidence validator configured", checks, resources)
            ok, why = self._evidence_check(req if req is not None else args)
            if not ok:
                return AuthzResult(DENY, "missing_evidence", why, checks, resources)
        # 9. approval
        if spec.requires_approval:
            checks.append("approval")
            if self._approval_state is None or req is None:
                return AuthzResult(DENY, "missing_approval", "approval state unavailable", checks, resources)
            appr = self._approval_state(str(args["request_id"]))
            if appr is None:
                return AuthzResult(DENY, "missing_approval", "no approval record", checks, resources)
            if appr.get("error"):
                return AuthzResult(DENY, str(appr.get("reason", "invalid_approval")), str(appr["error"]), checks, resources)
            if appr.get("request_hash") != req.get("hash"):
                return AuthzResult(DENY, "hash_mismatch", "approval bound to a different request hash", checks, resources)
            if appr.get("decision") != "approved":
                return AuthzResult(DENY, "rejected", "request was rejected", checks, resources)
            scope = set(appr.get("scope") or [])
            if not set(resources) <= scope:
                return AuthzResult(DENY, "approval_scope_exceeded", f"resources {sorted(set(resources) - scope)} not in approved scope", checks, resources)
            approver = self.store.get(str(appr.get("approver", "")))
            if approver is None or not approver.has("APPROVAL_APPEND", f"approval/{args['request_id']}"):
                return AuthzResult(DENY, "invalid_approval", "approver lacks APPROVAL_APPEND for this request", checks, resources)
            if appr.get("approver") == req.get("requester"):
                return AuthzResult(DENY, "self_approval", "requester cannot approve its own request", checks, resources)
        # 10. content policy (deterministic rules over the payload)
        if self._policy_check is not None:
            checks.append("policy")
            ok, why = self._policy_check(ctx, function_id, args)
            if not ok:
                return AuthzResult(DENY, "policy_block", why, checks, resources)
        checks.append("allow")
        return AuthzResult(ALLOW, "", "", checks, resources)

    # ------------------------------------------------------------ profile
    def profile(self, ctx: AgentContext) -> dict:
        principal = self.store.get(ctx.agent_id)
        if principal is None:
            return {"agent_id": ctx.agent_id, "capabilities": [], "permitted_functions": [], "authorization_version": self.store.version}
        permitted = []
        for fid in self.registry.ids():
            spec = self.registry.get(fid)
            if spec and spec.permission in principal.permissions():
                permitted.append({"function": fid, "permission": spec.permission, "consequential": spec.consequential,
                                  "requires_evidence": spec.requires_evidence, "requires_approval": spec.requires_approval,
                                  "description": spec.description})
        return {
            "agent_id": ctx.agent_id,
            "session_id": ctx.session_id,
            "capabilities": [{"permission": c.permission, "scope": c.scope} for c in principal.capabilities],
            "permitted_functions": permitted,
            "authorization_version": f"{self.store.version}:{self.store.sha256[:12]}",
            "note": "informational; the kernel re-checks authorization on every call",
        }


def canonical_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def new_request_id() -> str:
    return f"req-{time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:16]}"
