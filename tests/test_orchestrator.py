"""三段式契约 + 写作用域门禁 + 编排器:过闸/打回/续跑/上游失效。

跑:python tests/test_orchestrator.py  或  pytest tests/test_orchestrator.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.orchestrator import Orchestrator, run_case  # noqa: E402
from core.stage_contracts import (  # noqa: E402
    StageVerdict,
    validate_actions,
    validate_evidence,
    validate_spec,
)
from core.stage_runner import enforce_write_scope, write_scope  # noqa: E402


# ── 子 Agent 测试替身 ──

class _Spec:
    def __init__(self, value: str = "A") -> None:
        self.value = value

    def produce(self, stage, context):
        return {"exec_spec": {"case_id": context.case_id, "mode": "ui",
                              "verify_status": "human_verified", "ui": {"v": self.value}}}


class _Actions:
    def __init__(self) -> None:
        self.calls = 0

    def produce(self, stage, context):
        assert context.upstream_artifact("spec")["case_id"] == context.case_id
        self.calls += 1
        if self.calls == 1:  # 首次缺 from_spec/evidence -> 打回后重试
            return {"actions": {"status": "ok", "steps": [{"index": 0}], "evidence": []}}
        v = context.upstream_artifact("spec")["ui"]["v"]
        return {"actions": {"status": "ok",
                            "steps": [{"index": 0, "from_spec": "ui.actions[0]", "upstream_v": v}],
                            "evidence": ["shot.png"]}}


class _Evidence:
    def produce(self, stage, context):
        return {"evidence": {"verdict": "pass", "sources": {"ui": True, "api": True, "db": True},
                            "evidence_sha256": {"shot.png": "h"}}}


class _BadScope:
    def produce(self, stage, context):
        return {"exec_spec": {"case_id": context.case_id, "mode": "ui",
                              "verify_status": "human_verified", "ui": {"x": 1}},
                "actions": {"hack": 1}}


class _AlwaysBad:
    def produce(self, stage, context):
        return {"actions": {"status": "error", "steps": [], "evidence": []}}


def test_contracts_accept_and_reject():
    assert validate_spec({"exec_spec": {"case_id": "C1", "mode": "ui",
                                        "verify_status": "human_verified", "ui": {"p": 1}}}).ok
    assert not validate_spec({"exec_spec": {"case_id": "C1", "mode": "zzz",
                                            "verify_status": "draft"}}).ok
    assert validate_actions({"actions": {"status": "ok",
                                         "steps": [{"index": 0, "from_spec": "s"}],
                                         "evidence": ["x.png"]}}).ok
    assert not validate_actions({"actions": {"status": "safety_blocked", "steps": [],
                                             "evidence": [], "safety": {"blocked": True}}}).ok
    assert validate_evidence({"evidence": {"verdict": "pass",
                                           "sources": {"ui": True, "api": True, "db": False},
                                           "evidence_sha256": {"x.png": "h"}}}).ok
    assert not validate_evidence({"evidence": {"verdict": "", "sources": {"ui": True},
                                               "evidence_sha256": {}}}).ok


def test_write_scope_gate():
    assert write_scope("spec") == {"exec_spec"}
    assert enforce_write_scope("spec", {"exec_spec": {}}) == []
    violations = enforce_write_scope("spec", {"exec_spec": {}, "actions": {}})
    assert violations and "actions" in violations[0]


def test_happy_path_with_bounded_retry_and_resume():
    agents = {"spec": _Spec(), "actions": _Actions(), "evidence": _Evidence()}
    with tempfile.TemporaryDirectory() as directory:
        first = run_case(agents, directory, "C1", max_retries=1)
        assert first.completed and first.stopped_at == ""
        actions_outcome = next(o for o in first.outcomes if o.stage == "actions")
        assert actions_outcome.attempts == 2  # 首次打回 + 重试过闸
        second = run_case(agents, directory, "C1", max_retries=1)
        assert second.completed and all(o.reused for o in second.outcomes)


def test_scope_violation_stops_at_stage():
    agents = {"spec": _BadScope(), "actions": _Actions(), "evidence": _Evidence()}
    with tempfile.TemporaryDirectory() as directory:
        result = run_case(agents, directory, "C2")
        assert not result.completed and result.stopped_at == "spec"
        assert any("越界" in reason for reason in result.outcomes[0].reasons)


def test_reject_is_bounded_not_infinite():
    agents = {"spec": _Spec(), "actions": _AlwaysBad(), "evidence": _Evidence()}
    with tempfile.TemporaryDirectory() as directory:
        result = run_case(agents, directory, "C3", max_retries=2)
        assert not result.completed and result.stopped_at == "actions"
        assert result.outcomes[-1].attempts == 3  # 1 + 2 retries,有界


def test_upstream_change_invalidates_downstream():
    with tempfile.TemporaryDirectory() as directory:
        run_case({"spec": _Spec("A"), "actions": _Actions(), "evidence": _Evidence()},
                 directory, "C4")
        orch = Orchestrator({"spec": _Spec("B"), "actions": _Actions(), "evidence": _Evidence()},
                            directory, case_id="C4")
        # 让 spec 段重跑(清其 checkpoint),验证下游不复用旧产物、拾取新上游
        (orch.root / "stage_checkpoint.json").write_text("{}", encoding="utf-8")
        result = orch.run()
        assert result.completed and all(not o.reused for o in result.outcomes)
        actions = json.loads((orch.root / "artifacts" / "actions.json").read_text(encoding="utf-8"))
        assert actions["actions"]["steps"][0]["upstream_v"] == "B"


def main() -> None:
    test_contracts_accept_and_reject()
    test_write_scope_gate()
    test_happy_path_with_bounded_retry_and_resume()
    test_scope_violation_stops_at_stage()
    test_reject_is_bounded_not_infinite()
    test_upstream_change_invalidates_downstream()
    print("test_orchestrator ✅ 全部通过")


if __name__ == "__main__":
    main()
