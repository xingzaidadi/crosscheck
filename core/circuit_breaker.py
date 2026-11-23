"""Global circuit breaker: deterministic stop condition for AI self-heal loops.

Reuses the ``consecutive_failures`` semantics already used by ``asset_health`` but
applies them inside the execution loop so the tool stops retrying the same problem
after N rounds and hands off to a human, instead of looping indefinitely.

The breaker only *stops*. It does not change verdicts, auto-fix, or downgrade
report wording. Counting is keyed on ``(case_id, failure_class)`` so that only the
*same* failure recurring counts as "the same unsolved problem".
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.failure_class import FailureClass

# Failures that are consumable by retry / self-heal and therefore count toward a trip.
_COUNT_CLASSES: frozenset[FailureClass] = frozenset({
    FailureClass.TARGET_FAIL,
    FailureClass.CAPABILITY_DRIFT,
    FailureClass.PREREQUISITE_FAILED,
    FailureClass.ENV_ERROR,
    FailureClass.UNKNOWN,
})

# Terminal failures that should stop on their own path and never trip the breaker.
_SKIP_CLASSES: frozenset[FailureClass] = frozenset({
    FailureClass.SPEC_ERROR,
    FailureClass.PLAN_ERROR,
    FailureClass.SAFETY_BLOCKED,
    FailureClass.CLEANUP_FAILED,
})


@dataclass(frozen=True)
class BreakerPolicy:
    default_threshold: int = 3
    env_threshold: int = 2
    count_classes: frozenset[FailureClass] = _COUNT_CLASSES
    skip_classes: frozenset[FailureClass] = _SKIP_CLASSES

    def __post_init__(self) -> None:
        if self.default_threshold < 1 or self.env_threshold < 1:
            raise ValueError("breaker thresholds must be positive")

    def threshold_for(self, failure_class: FailureClass) -> int:
        if failure_class is FailureClass.ENV_ERROR:
            return self.env_threshold
        return self.default_threshold


def default_policy() -> BreakerPolicy:
    return BreakerPolicy()


@dataclass
class BreakerState:
    counters: dict[tuple[str, str], int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, int]:
        return {f"{case_id}::{failure}": count for (case_id, failure), count in self.counters.items()}

    @classmethod
    def from_dict(cls, data: dict[str, int] | None) -> "BreakerState":
        counters: dict[tuple[str, str], int] = {}
        for key, count in (data or {}).items():
            case_id, _, failure = key.partition("::")
            counters[(case_id, failure)] = int(count)
        return cls(counters=counters)


@dataclass(frozen=True)
class BreakerDecision:
    tripped: bool
    case_id: str
    failure_class: str
    attempts: int
    threshold: int
    reason: str


def observe(
    state: BreakerState,
    policy: BreakerPolicy,
    *,
    case_id: str,
    failure_class: FailureClass | None,
    success: bool,
) -> BreakerDecision:
    """Record one execution round and decide whether to trip.

    - ``success=True`` resets every counter for this case and never trips.
    - A failure whose class is not countable does not change counters and never trips.
    - A countable failure increments ``(case_id, class)`` and trips at the threshold.
    """
    if success:
        _reset_case(state, case_id)
        return BreakerDecision(False, case_id, "", 0, policy.default_threshold,
                               "success resets breaker")

    if failure_class is None or failure_class not in policy.count_classes or failure_class in policy.skip_classes:
        name = failure_class.value if failure_class is not None else ""
        return BreakerDecision(False, case_id, name, 0, policy.default_threshold,
                               "failure class not counted toward breaker")

    key = (case_id, failure_class.value)
    attempts = state.counters.get(key, 0) + 1
    state.counters[key] = attempts
    threshold = policy.threshold_for(failure_class)
    tripped = attempts >= threshold
    reason = (f"same failure {failure_class.value} repeated {attempts} times (>= {threshold})"
              if tripped else f"failure {failure_class.value} attempt {attempts}/{threshold}")
    return BreakerDecision(tripped, case_id, failure_class.value, attempts, threshold, reason)


def _reset_case(state: BreakerState, case_id: str) -> None:
    # Delete (not zero) so resolved cases don't accumulate dead keys in the
    # persisted state across long-running suites. A missing key == count 0.
    for key in [k for k in state.counters if k[0] == case_id]:
        del state.counters[key]


def build_handoff(
    decision: BreakerDecision,
    *,
    run_id: str,
    triage_bucket: str = "",
    last_verdict: str = "",
    last_details: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    suggested_action: str = "",
) -> dict[str, Any]:
    """Build a deterministic, hash-bound human-handoff packet for a tripped breaker."""
    packet: dict[str, Any] = {
        "schema_version": 1,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "BLOCKED_NEEDS_HUMAN",
        "case_id": decision.case_id,
        "failure_class": decision.failure_class,
        "attempts": decision.attempts,
        "threshold": decision.threshold,
        "reason": decision.reason,
        "triage_bucket": triage_bucket,
        "last_verdict": last_verdict,
        "last_details": list(last_details or []),
        "evidence_refs": list(evidence_refs or []),
        "suggested_action": suggested_action,
        "run_id": run_id,
    }
    hashable = {k: v for k, v in packet.items() if k not in {"content_hash", "at"}}
    digest = hashlib.sha256(
        json.dumps(hashable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    packet["content_hash"] = f"sha256:{digest}"
    return packet


def append_handoff(reports_dir: str | Path, packet: dict[str, Any]) -> Path:
    root = Path(reports_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "blocked_needs_human.jsonl"
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(packet, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def read_handoffs(reports_dir: str | Path) -> list[dict[str, Any]]:
    path = Path(reports_dir) / "blocked_needs_human.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
