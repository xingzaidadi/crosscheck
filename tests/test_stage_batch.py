"""三段式批量入口:多用例 + 熔断复用 + 转人工包。

跑:python tests/test_stage_batch.py  或  pytest tests/test_stage_batch.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.circuit_breaker import BreakerPolicy  # noqa: E402
from core.failure_class import FailureClass  # noqa: E402
from core.orchestrator import OrchestrationResult  # noqa: E402
from core.stage_batch import classify_outcome, run_batch  # noqa: E402


class _Spec:
    def __init__(self, verified: bool = True) -> None:
        self.verified = verified

    def produce(self, stage, context):
        status = "human_verified" if self.verified else "draft"
        return {"exec_spec": {"case_id": context.case_id, "mode": "ui",
                              "verify_status": status, "ui": {"p": 1}}}


class _Actions:
    def produce(self, stage, context):
        return {"actions": {"status": "ok", "steps": [{"index": 0, "from_spec": "ui"}],
                            "evidence": ["s.png"], "evidence_sha256": {"s.png": "h"}}}


class _ActionsSafety:
    def produce(self, stage, context):
        return {"actions": {"status": "safety_blocked", "steps": [], "evidence": [],
                            "safety": {"blocked": True, "reason": "write guard"}}}


class _EvidenceBad:
    def produce(self, stage, context):
        return {"evidence": {"verdict": "", "sources": {"ui": True}, "evidence_sha256": {}}}


class _EvidenceOk:
    def produce(self, stage, context):
        return {"evidence": {"verdict": "pass", "sources": {"ui": True, "api": True, "db": True},
                            "evidence_sha256": {"s.png": "h"}}}


def _outcome(stage, verdict, reasons=None):
    from core.orchestrator import StageOutcome
    return StageOutcome(stage=stage, verdict=verdict, reasons=reasons or [])


def test_classify_outcome_maps_failure_classes():
    ok = OrchestrationResult("C1", True, outcomes=[])
    assert classify_outcome(ok) == (True, None)

    spec_stop = OrchestrationResult("C1", False, stopped_at="spec",
                                    outcomes=[_outcome("spec", "reject", ["draft"])])
    assert classify_outcome(spec_stop) == (False, FailureClass.SPEC_ERROR)

    safety = OrchestrationResult("C1", False, stopped_at="actions",
                                 outcomes=[_outcome("actions", "reject", ["命中安全阻断: x"])])
    assert classify_outcome(safety) == (False, FailureClass.SAFETY_BLOCKED)

    target = OrchestrationResult("C1", False, stopped_at="evidence",
                                 outcomes=[_outcome("evidence", "reject", ["证据缺哈希"])])
    assert classify_outcome(target) == (False, FailureClass.TARGET_FAIL)


def test_breaker_trips_on_repeated_target_fail():
    agents = {"spec": _Spec(), "actions": _Actions(), "evidence": _EvidenceBad()}
    with tempfile.TemporaryDirectory() as directory:
        batch = run_batch(agents, directory, ["C1", "C1", "C1", "C1", "C1"],
                          max_retries=0, policy=BreakerPolicy(default_threshold=3))
        assert batch.stopped
        assert len(batch.results) == 3  # 第 3 次触发熔断即停批
        assert os.path.exists(batch.handoff_path)
        packet = json.loads(Path(batch.handoff_path).read_text(encoding="utf-8").splitlines()[-1])
        assert packet["status"] == "BLOCKED_NEEDS_HUMAN" and packet["case_id"] == "C1"


def test_spec_error_never_trips():
    agents = {"spec": _Spec(verified=False), "actions": _Actions(), "evidence": _EvidenceBad()}
    with tempfile.TemporaryDirectory() as directory:
        batch = run_batch(agents, directory, ["A", "A", "A", "A"],
                          max_retries=0, policy=BreakerPolicy(default_threshold=2))
        assert not batch.stopped and len(batch.results) == 4


def test_safety_blocked_never_trips():
    agents = {"spec": _Spec(), "actions": _ActionsSafety(), "evidence": _EvidenceOk()}
    with tempfile.TemporaryDirectory() as directory:
        batch = run_batch(agents, directory, ["B", "B", "B"],
                          max_retries=0, policy=BreakerPolicy(default_threshold=2))
        assert not batch.stopped and len(batch.results) == 3


def test_all_pass_batch_completes():
    agents = {"spec": _Spec(), "actions": _Actions(), "evidence": _EvidenceOk()}
    with tempfile.TemporaryDirectory() as directory:
        batch = run_batch(agents, directory, ["X", "Y", "Z"], max_retries=0)
        assert not batch.stopped
        assert all(result.completed for result in batch.results)


def main() -> None:
    test_classify_outcome_maps_failure_classes()
    test_breaker_trips_on_repeated_target_fail()
    test_spec_error_never_trips()
    test_safety_blocked_never_trips()
    test_all_pass_batch_completes()
    print("test_stage_batch ✅ 全部通过")


if __name__ == "__main__":
    main()
