from core.circuit_breaker import (
    BreakerPolicy,
    BreakerState,
    observe,
    default_policy,
)
from core.failure_class import FailureClass


def _state() -> BreakerState:
    return BreakerState(counters={})


def test_success_resets_counter_and_does_not_trip():
    state = _state()
    policy = default_policy()
    observe(state, policy, case_id="TC1", failure_class=FailureClass.TARGET_FAIL, success=False)
    decision = observe(state, policy, case_id="TC1", failure_class=None, success=True)
    assert decision.tripped is False
    assert state.counters.get(("TC1", "TARGET_FAIL"), 0) == 0


def test_three_consecutive_same_class_failures_trip():
    state = _state()
    policy = default_policy()
    first = observe(state, policy, case_id="TC1", failure_class=FailureClass.TARGET_FAIL, success=False)
    second = observe(state, policy, case_id="TC1", failure_class=FailureClass.TARGET_FAIL, success=False)
    third = observe(state, policy, case_id="TC1", failure_class=FailureClass.TARGET_FAIL, success=False)
    assert first.tripped is False
    assert second.tripped is False
    assert third.tripped is True
    assert third.attempts == 3
    assert third.threshold == 3


def test_different_failure_classes_do_not_accumulate_together():
    state = _state()
    policy = default_policy()
    observe(state, policy, case_id="TC1", failure_class=FailureClass.ENV_ERROR, success=False)
    decision = observe(state, policy, case_id="TC1", failure_class=FailureClass.TARGET_FAIL, success=False)
    assert decision.tripped is False
    assert state.counters[("TC1", "ENV_ERROR")] == 1
    assert state.counters[("TC1", "TARGET_FAIL")] == 1


def test_env_error_uses_lower_threshold():
    state = _state()
    policy = default_policy()
    observe(state, policy, case_id="TC1", failure_class=FailureClass.ENV_ERROR, success=False)
    decision = observe(state, policy, case_id="TC1", failure_class=FailureClass.ENV_ERROR, success=False)
    assert decision.tripped is True
    assert decision.attempts == 2
    assert decision.threshold == 2


def test_spec_error_never_trips_and_is_not_counted():
    state = _state()
    policy = default_policy()
    for _ in range(5):
        decision = observe(state, policy, case_id="TC1", failure_class=FailureClass.SPEC_ERROR, success=False)
        assert decision.tripped is False
    assert ("TC1", "SPEC_ERROR") not in state.counters


def test_safety_blocked_never_trips():
    state = _state()
    policy = default_policy()
    for _ in range(5):
        decision = observe(state, policy, case_id="TC1", failure_class=FailureClass.SAFETY_BLOCKED, success=False)
        assert decision.tripped is False


def test_counters_are_per_case():
    state = _state()
    policy = default_policy()
    observe(state, policy, case_id="TC1", failure_class=FailureClass.TARGET_FAIL, success=False)
    observe(state, policy, case_id="TC1", failure_class=FailureClass.TARGET_FAIL, success=False)
    decision_other = observe(state, policy, case_id="TC2", failure_class=FailureClass.TARGET_FAIL, success=False)
    assert decision_other.tripped is False
    assert decision_other.attempts == 1


def test_state_roundtrips_through_registry_dict():
    state = _state()
    policy = default_policy()
    observe(state, policy, case_id="TC1", failure_class=FailureClass.TARGET_FAIL, success=False)
    observe(state, policy, case_id="TC1", failure_class=FailureClass.TARGET_FAIL, success=False)
    snapshot = state.to_dict()
    restored = BreakerState.from_dict(snapshot)
    decision = observe(restored, policy, case_id="TC1", failure_class=FailureClass.TARGET_FAIL, success=False)
    assert decision.tripped is True
    assert decision.attempts == 3


def test_custom_threshold_overrides_default():
    state = _state()
    policy = BreakerPolicy(default_threshold=2)
    observe(state, policy, case_id="TC1", failure_class=FailureClass.TARGET_FAIL, success=False)
    decision = observe(state, policy, case_id="TC1", failure_class=FailureClass.TARGET_FAIL, success=False)
    assert decision.tripped is True
    assert decision.threshold == 2


def test_success_deletes_keys_rather_than_zeroing():
    state = _state()
    policy = default_policy()
    observe(state, policy, case_id="TC1", failure_class=FailureClass.TARGET_FAIL, success=False)
    observe(state, policy, case_id="TC1", failure_class=FailureClass.ENV_ERROR, success=False)
    observe(state, policy, case_id="TC1", failure_class=None, success=True)
    # No dead keys left behind for the resolved case (prevents state bloat).
    assert all(key[0] != "TC1" for key in state.counters)
    assert state.to_dict() == {}
