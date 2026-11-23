"""Global circuit breaker wired into the case-level pipeline runner."""
from __future__ import annotations

from types import SimpleNamespace

from core.circuit_breaker import BreakerPolicy, read_handoffs
from core.interfaces import CaseResult, Verdict
from core.pipeline_runner import run_pipeline


def _spec(case_id, mode="reconcile"):
    return SimpleNamespace(case_id=case_id, mode=mode)


def test_repeated_same_case_failure_trips_global_breaker(tmp_path):
    specs = [_spec("TC1")]
    policy = BreakerPolicy(default_threshold=3)

    def always_fail(spec):
        return CaseResult(spec.case_id, Verdict.FAIL, details=["字段未找到: order_no"])

    # Re-running a failing case (resume=False clears the checkpoint each time) accumulates
    # breaker state across runs via the separate persisted breaker_state.json.
    out1 = run_pipeline(specs, always_fail, tmp_path, pilot_size=0, resume=False, breaker_policy=policy)
    assert out1.stopped is False  # attempt 1, not tripped yet

    out2 = run_pipeline(specs, always_fail, tmp_path, pilot_size=0, resume=False, breaker_policy=policy)
    assert out2.stopped is False  # attempt 2

    out3 = run_pipeline(specs, always_fail, tmp_path, pilot_size=0, resume=False, breaker_policy=policy)
    assert out3.stopped is True
    assert "BLOCKED_NEEDS_HUMAN" in out3.reason

    handoffs = read_handoffs(tmp_path)
    assert len(handoffs) == 1
    assert handoffs[0]["case_id"] == "TC1"
    assert handoffs[0]["failure_class"] == "TARGET_FAIL"
    assert handoffs[0]["attempts"] == 3
    assert handoffs[0]["content_hash"].startswith("sha256:")


def test_passing_case_does_not_trip_or_handoff(tmp_path):
    specs = [_spec("TC1")]
    policy = BreakerPolicy(default_threshold=3)
    for _ in range(4):
        out = run_pipeline(specs, lambda s: CaseResult(s.case_id, Verdict.PASS),
                           tmp_path, pilot_size=0, resume=False, breaker_policy=policy)
        assert out.stopped is False
    assert read_handoffs(tmp_path) == []


def test_intervening_pass_resets_and_prevents_trip(tmp_path):
    specs = [_spec("TC1")]
    policy = BreakerPolicy(default_threshold=3)
    verdicts = [Verdict.FAIL, Verdict.FAIL, Verdict.PASS, Verdict.FAIL, Verdict.FAIL]
    for verdict in verdicts:
        out = run_pipeline(specs, lambda s, v=verdict: CaseResult(s.case_id, v),
                           tmp_path, pilot_size=0, resume=False, breaker_policy=policy)
        assert out.stopped is False  # pass in the middle resets the counter
    assert read_handoffs(tmp_path) == []


def test_default_resume_path_still_trips_on_repeated_failure(tmp_path):
    """Default resume=True must NOT make the breaker a no-op: a case that keeps
    failing across resumed runs on the same run_dir must still trip."""
    specs = [_spec("TC1")]
    policy = BreakerPolicy(default_threshold=3)

    def always_fail(spec):
        return CaseResult(spec.case_id, Verdict.FAIL, details=["字段未找到: order_no"])

    out1 = run_pipeline(specs, always_fail, tmp_path, pilot_size=0, breaker_policy=policy)
    out2 = run_pipeline(specs, always_fail, tmp_path, pilot_size=0, breaker_policy=policy)
    out3 = run_pipeline(specs, always_fail, tmp_path, pilot_size=0, breaker_policy=policy)

    assert out3.stopped is True
    assert "BLOCKED_NEEDS_HUMAN" in out3.reason
    handoffs = read_handoffs(tmp_path)
    assert len(handoffs) == 1
    assert handoffs[0]["attempts"] == 3


def test_cleanup_failure_does_not_trip_breaker_even_with_target_fail_class(tmp_path):
    """A dirty environment (cleanup_ok=False) must be reported as cleanup failure,
    not masked by a repeated-failure trip, even if failure_class says TARGET_FAIL."""
    specs = [_spec("TC1")]
    policy = BreakerPolicy(default_threshold=2)

    def fail_with_dirty_cleanup(spec):
        r = CaseResult(spec.case_id, Verdict.FAIL, cleanup_ok=False)
        r.failure_class = "TARGET_FAIL"
        return r

    out = run_pipeline(specs, fail_with_dirty_cleanup, tmp_path, pilot_size=0,
                       resume=False, breaker_policy=policy)
    # Cleanup stop wins; no breaker handoff.
    assert "cleanup failed" in out.reason
    assert read_handoffs(tmp_path) == []


def test_breaker_defaults_off_preserves_legacy_behavior(tmp_path):
    specs = [_spec("TC1")]
    # No breaker_policy passed -> global breaker disabled, legacy run unaffected.
    out = run_pipeline(specs, lambda s: CaseResult(s.case_id, Verdict.FAIL),
                       tmp_path, pilot_size=0)
    assert out.stopped is False
    assert read_handoffs(tmp_path) == []
