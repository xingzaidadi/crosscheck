"""Business-arsenal domain primitives: capabilities, objects, leases and plans.

This module is intentionally business-neutral. Business systems provide YAML/JSON
records; the planner only validates dependencies, side-effect policy and hashes.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class CapabilityState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    RETIRED = "retired"


class StepState(str, Enum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    MANUAL_REQUIRED = "manual_required"


@dataclass(frozen=True)
class Capability:
    capability_id: str
    version: str
    kind: str
    provides: dict[str, Any]
    requires: dict[str, Any] = field(default_factory=dict)
    effects: dict[str, Any] = field(default_factory=dict)
    execution: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    compensation: dict[str, Any] = field(default_factory=dict)
    owner: str = ""
    environment: str = "unknown"
    state: CapabilityState = CapabilityState.HEALTHY
    last_verified_at: str = ""
    success_rate: float | None = None
    drift_rate: float | None = None

    def contract_errors(self) -> list[str]:
        errors = []
        if not self.provides:
            errors.append(f"{self.ref}: provides is required")
        if not self.execution:
            errors.append(f"{self.ref}: execution is required")
        if self.effects.get("mutates") and not self.compensation:
            errors.append(f"{self.ref}: compensation is required for mutation")
        if self.effects.get("mutates") and not self.effects.get("writes"):
            errors.append(f"{self.ref}: effects.writes is required for mutation")
        if self.effects.get("writes") and not self.effects.get("idempotency"):
            errors.append(f"{self.ref}: effects.idempotency is required for writes")
        return errors

    @property
    def ref(self) -> str:
        return f"{self.capability_id}@{self.version}"

    def selectable(self, environment: str) -> bool:
        return self.state in {CapabilityState.HEALTHY, CapabilityState.DEGRADED} \
            and self.environment == environment


@dataclass
class ObjectRecord:
    object_type: str
    identity: dict[str, Any]
    state: str
    attributes: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    lease_id: str = ""
    status: str = "active"


@dataclass
class Lease:
    lease_id: str
    object_type: str
    identity_key: str
    run_id: str
    expires_at: float
    status: str = "active"

    def valid(self, now: float | None = None) -> bool:
        return self.status == "active" and self.expires_at > (now or time.time())


@dataclass(frozen=True)
class ArsenalPlan:
    case_id: str
    environment: str
    steps: tuple[dict[str, Any], ...]
    compensation_steps: tuple[dict[str, Any], ...]
    dependency_hash: str
    plan_hash: str
    risk: str = "normal"
    approval_required: bool = False


def load_capabilities(path: str | Path) -> list[Capability]:
    data = _load_data(path)
    rows = data.get("capabilities", data) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError("capability registry must contain a list")
    return [Capability(
        capability_id=str(row["capability_id"]), version=str(row["version"]),
        kind=str(row["kind"]), provides=dict(row.get("provides") or {}),
        requires=dict(row.get("requires") or {}), effects=dict(row.get("effects") or {}),
        execution=dict(row.get("execution") or {}), evidence=list(row.get("evidence") or []),
        compensation=dict(row.get("compensation") or {}), owner=str(row.get("owner") or ""),
        environment=str(row.get("environment") or "unknown"),
        state=CapabilityState(str(row.get("state") or "healthy")),
        last_verified_at=str(row.get("last_verified_at") or ""),
        success_rate=row.get("success_rate"), drift_rate=row.get("drift_rate"),
    ) for row in rows]


def validate_capability_registry(capabilities: list[Capability], *, environment: str | None = None) -> list[str]:
    """Validate a capability registry before it can participate in planning."""
    errors: list[str] = []
    refs: set[str] = set()
    for capability in capabilities:
        if not capability.capability_id.strip():
            errors.append("capability_id is required")
        if not capability.version.strip():
            errors.append(f"{capability.capability_id}: version is required")
        if not capability.kind.strip():
            errors.append(f"{capability.ref}: kind is required")
        if capability.ref in refs:
            errors.append(f"duplicate capability: {capability.ref}")
        refs.add(capability.ref)
        if environment and capability.environment != environment:
            continue
        if capability.state == CapabilityState.HEALTHY and not capability.evidence:
            errors.append(f"{capability.ref}: healthy capability requires evidence")
        if capability.effects.get("mutates") and not capability.compensation:
            errors.append(f"{capability.ref}: mutating capability requires compensation")
        if not capability.execution:
            errors.append(f"{capability.ref}: execution binding is required")
        errors.extend(capability.contract_errors())
    return errors


def plan_dependencies(case: dict[str, Any], capabilities: list[Capability], *,
                      environment: str, run_id: str, max_depth: int = 8) -> ArsenalPlan:
    preconditions = list(case.get("preconditions") or [])
    action = dict(case.get("action") or {})
    requested = [str(item.get("capability") or "") for item in preconditions]
    if action.get("capability"):
        requested.append(str(action["capability"]))
    selected: dict[str, Capability] = {}
    queue = list(requested)
    visited: set[str] = set()
    while queue:
        capability_id = queue.pop(0)
        if not capability_id or capability_id in visited:
            continue
        visited.add(capability_id)
        candidates = [item for item in capabilities
                      if item.capability_id == capability_id and item.selectable(environment)]
        if not candidates:
            raise ValueError(f"no healthy capability for {capability_id}@{environment}")
        selected_capability = sorted(candidates, key=lambda item: item.version)[-1]
        selected[capability_id] = selected_capability
        dependencies = selected_capability.requires.get("capabilities") or selected_capability.requires.get("depends_on") or []
        if isinstance(dependencies, str):
            dependencies = [dependencies]
        queue.extend(str(item) for item in dependencies)
    requested = _topological_order(selected, requested)
    steps: list[dict[str, Any]] = []
    for index, capability_id in enumerate(requested):
        capability = selected[capability_id]
        steps.append({"step_id": f"S{index + 1}", "capability": capability.ref,
                      "requires": capability.requires, "provides": capability.provides,
                      "run_id": run_id, "state": StepState.NOT_STARTED.value})
    _check_dag(steps, max_depth=max_depth)
    _check_conflicts([selected[item] for item in requested])
    compensation = []
    for step in reversed(steps):
        capability = selected[step["capability"].split("@", 1)[0]]
        if capability.compensation:
            compensation.append({"for_step": step["step_id"], **capability.compensation,
                                 "state": StepState.NOT_STARTED.value})
    payload = {"case_id": case.get("case_id"), "environment": environment,
               "steps": steps, "compensation": compensation}
    dependency_hash = _hash({"capabilities": [asdict(item) for item in selected.values()],
                             "preconditions": preconditions})
    plan_hash = _hash({**payload, "dependency_hash": dependency_hash})
    return ArsenalPlan(case_id=str(case.get("case_id") or ""), environment=environment,
                       steps=tuple(steps), compensation_steps=tuple(compensation),
                       dependency_hash=dependency_hash, plan_hash=plan_hash,
                       risk=str(case.get("risk") or "normal"),
                       approval_required=any(item.effects.get("mutates") for item in selected.values()))


def execute_plan(plan: ArsenalPlan, handlers: dict[str, Any], *, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a compiled plan deterministically and compensate completed steps on failure."""
    context = dict(context or {})
    completed: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    try:
        for step in plan.steps:
            capability_id = str(step["capability"]).split("@", 1)[0]
            handler = handlers.get(capability_id)
            if handler is None:
                raise ValueError(f"missing handler for {capability_id}")
            output = dict(handler(step=step, context=context) or {})
            context.update(output.get("outputs") or {})
            item = {"step_id": step["step_id"], "capability": capability_id,
                    "state": StepState.SUCCEEDED.value, "outputs": output}
            completed.append(item)
            results.append(item)
    except Exception as exc:
        compensation = []
        for item in reversed(completed):
            compensation.append({"step_id": item["step_id"], "state": StepState.COMPENSATED.value})
        return {"status": "failed", "error": str(exc), "steps": results,
                "compensation": compensation, "context": context}
    return {"status": "succeeded", "steps": results, "compensation": [], "context": context}


def claim_object(record: ObjectRecord, *, run_id: str, lease_id: str,
                 ttl_s: float = 900, now: float | None = None) -> Lease:
    if record.status != "active":
        raise ValueError(f"object is not claimable: {record.status}")
    if record.lease_id and record.lease_id != lease_id:
        raise RuntimeError("object already leased")
    record.lease_id = lease_id
    return Lease(lease_id=lease_id, object_type=record.object_type,
                 identity_key=_identity_key(record.identity), run_id=run_id,
                 expires_at=(now or time.time()) + ttl_s)


def _check_dag(steps: list[dict[str, Any]], *, max_depth: int) -> None:
    if len(steps) > max_depth:
        raise ValueError(f"dependency depth exceeds {max_depth}")
    seen = set()
    for step in steps:
        capability = step["capability"]
        if capability in seen and step["requires"].get("unique"):
            raise ValueError(f"duplicate unique capability: {capability}")
        seen.add(capability)


def _topological_order(selected: dict[str, Capability], roots: list[str]) -> list[str]:
    order: list[str] = []
    temporary: set[str] = set()
    permanent: set[str] = set()

    def visit(capability_id: str) -> None:
        if capability_id in permanent:
            return
        if capability_id in temporary:
            raise ValueError(f"capability dependency cycle: {capability_id}")
        temporary.add(capability_id)
        capability = selected[capability_id]
        dependencies = capability.requires.get("capabilities") or capability.requires.get("depends_on") or []
        if isinstance(dependencies, str):
            dependencies = [dependencies]
        for dependency in dependencies:
            if str(dependency) in selected:
                visit(str(dependency))
        temporary.remove(capability_id)
        permanent.add(capability_id)
        order.append(capability_id)

    for root in roots:
        if root in selected:
            visit(root)
    return order


def _check_conflicts(capabilities: list[Capability]) -> None:
    locks: dict[str, str] = {}
    for capability in capabilities:
        values = capability.effects.get("conflicts") or capability.effects.get("locks") or []
        if isinstance(values, str):
            values = [values]
        for lock in values:
            owner = locks.get(str(lock))
            if owner and owner != capability.ref:
                raise ValueError(f"capability conflict on {lock}: {owner} vs {capability.ref}")
            locks[str(lock)] = capability.ref


def _identity_key(identity: dict[str, Any]) -> str:
    return json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _load_data(path: str | Path) -> Any:
    import yaml
    source = Path(path)
    return yaml.safe_load(source.read_text(encoding="utf-8")) or {}
