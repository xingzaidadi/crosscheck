import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.failure_class import FailureClass, classify_verdict  # noqa: E402


def test_gate_categories_map_to_documented_taxonomy():
    assert classify_verdict("blocked", blocked_category="DATA_NOT_READY") is FailureClass.PREREQUISITE_FAILED
    assert classify_verdict("blocked", blocked_category="TOOL_POLICY") is FailureClass.SAFETY_BLOCKED
    assert classify_verdict("blocked", blocked_category="AUTH_NOT_READY") is FailureClass.ENV_ERROR
    assert classify_verdict("fail") is FailureClass.TARGET_FAIL
    assert classify_verdict("pass") is None


def test_cleanup_has_priority_over_business_failure():
    assert classify_verdict("fail", cleanup_ok=False) is FailureClass.CLEANUP_FAILED


if __name__ == "__main__":
    test_gate_categories_map_to_documented_taxonomy()
    test_cleanup_has_priority_over_business_failure()
    print("failure class passed")
