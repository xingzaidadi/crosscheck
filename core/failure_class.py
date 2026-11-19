"""Canonical failure taxonomy shared by runners, reports, and acceptance gates."""
from __future__ import annotations

from enum import Enum


class FailureClass(str, Enum):
    SPEC_ERROR = "SPEC_ERROR"
    PLAN_ERROR = "PLAN_ERROR"
    SAFETY_BLOCKED = "SAFETY_BLOCKED"
    PREREQUISITE_FAILED = "PREREQUISITE_FAILED"
    ENV_ERROR = "ENV_ERROR"
    CAPABILITY_DRIFT = "CAPABILITY_DRIFT"
    TARGET_FAIL = "TARGET_FAIL"
    UNKNOWN = "UNKNOWN"
    CLEANUP_FAILED = "CLEANUP_FAILED"


def classify_verdict(verdict: str, *, blocked_category: str = "", cleanup_ok: bool = True,
                     target_assertion_failed: bool = False) -> FailureClass | None:
    """Map legacy verdicts and gate categories without changing verdict semantics."""
    if not cleanup_ok:
        return FailureClass.CLEANUP_FAILED
    if target_assertion_failed or verdict == "fail":
        return FailureClass.TARGET_FAIL
    if verdict == "invalid_spec":
        return FailureClass.SPEC_ERROR
    if verdict == "aborted":
        return FailureClass.SAFETY_BLOCKED
    if verdict == "blocked":
        return {
            "DATA_NOT_READY": FailureClass.PREREQUISITE_FAILED,
            "AUTH_NOT_READY": FailureClass.ENV_ERROR,
            "ENV_NOT_READY": FailureClass.ENV_ERROR,
            "TOOL_POLICY": FailureClass.SAFETY_BLOCKED,
            "SPEC_NOT_READY": FailureClass.SPEC_ERROR,
        }.get(blocked_category, FailureClass.PREREQUISITE_FAILED)
    if verdict == "env_error":
        return FailureClass.ENV_ERROR
    if verdict in {"partial", "skip"}:
        return FailureClass.UNKNOWN
    return None
