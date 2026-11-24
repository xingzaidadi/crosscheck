"""真实适配器:ExecSpec / AgentRuntimeResult / ReconcileResult 翻译为三段契约产物。

跑:python tests/test_stage_adapters.py  或  pytest tests/test_stage_adapters.py
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.orchestrator import run_case  # noqa: E402
from core.reconciler import ReconcileResult  # noqa: E402
from core.spec import ExecSpec  # noqa: E402
from core.stage_adapters import (  # noqa: E402
    ActionsAgent,
    EvidenceAgent,
    SpecAgent,
    reconcile_to_sources,
)
from core.stage_contracts import validate_actions, validate_evidence, validate_spec  # noqa: E402
from core.stage_runner import StageContext  # noqa: E402
from core.ui_agent.runtime import AgentRuntimeResult  # noqa: E402


def _ctx(stage, upstream=None):
    return StageContext(stage=stage, case_id="TC01", upstream=upstream or {})


def test_spec_agent_translates_execspec_and_marks_verified():
    def modeler(context):
        return ExecSpec(case_id=context.case_id, kind="write", mode="ui",
                        verify_status="draft", ui={"page_url": "http://x"},
                        assertions={"response": {"status": 200}})
    out = SpecAgent(modeler, auto_verify=True).produce("spec", _ctx("spec"))
    assert out["exec_spec"]["verify_status"] == "human_verified"
    assert validate_spec(out).ok


def test_spec_agent_default_keeps_draft_and_is_rejected():
    def modeler(context):
        return ExecSpec(case_id=context.case_id, mode="ui", verify_status="draft",
                        ui={"page_url": "http://x"})
    out = SpecAgent(modeler).produce("spec", _ctx("spec"))
    assert out["exec_spec"]["verify_status"] == "draft"
    assert not validate_spec(out).ok  # 不替人盖"已审"章


def test_actions_agent_backfills_from_spec_and_hashes_evidence():
    tmp = tempfile.mkdtemp()
    shot = os.path.join(tmp, "shot.png")
    open(shot, "wb").write(b"PNG")

    def runner(exec_spec, context):
        assert exec_spec["case_id"] == context.case_id
        return AgentRuntimeResult(status="PASSED",
                                  actions=[{"action": "click", "target": "#btn"}],
                                  evidence=[shot])
    upstream = {"exec_spec": {"case_id": "TC01"}}
    out = ActionsAgent(runner).produce("actions", _ctx("actions", upstream))
    step = out["actions"]["steps"][0]
    assert step["from_spec"] == "#btn" and step["index"] == 0
    assert out["actions"]["evidence_sha256"][shot]
    assert validate_actions(out).ok


def test_actions_agent_marks_safety_blocked():
    def runner(exec_spec, context):
        return AgentRuntimeResult(status="BLOCKED", error="write guard")
    out = ActionsAgent(runner).produce("actions", _ctx("actions", {"exec_spec": {"case_id": "TC01"}}))
    assert out["actions"]["status"] == "safety_blocked"
    assert out["actions"]["safety"]["blocked"] is True
    assert not validate_actions(out).ok


def test_evidence_agent_merges_hashes_and_sources():
    upstream = {"exec_spec": {"case_id": "TC01"},
                "actions": {"evidence_sha256": {"shot.png": "h1"}, "steps": [{"index": 0}]}}

    def verify(exec_spec, actions, context):
        rec = ReconcileResult(consistent=True, api_total=3, db_total=3, table="t1")
        return {"verdict": "pass",
                "sources": reconcile_to_sources(rec, ui=bool(actions.get("steps"))),
                "reconcile": rec}
    out = EvidenceAgent(verify).produce("evidence", _ctx("evidence", upstream))
    assert out["evidence"]["sources"] == {"ui": True, "api": True, "db": True}
    assert out["evidence"]["evidence_sha256"]["shot.png"] == "h1"
    assert out["evidence"]["reconcile"]["consistent"] is True
    assert validate_evidence(out).ok


def test_full_pipeline_through_real_adapters():
    tmp = tempfile.mkdtemp()
    shot = os.path.join(tmp, "shot.png")
    open(shot, "wb").write(b"PNG")

    def modeler(context):
        return ExecSpec(case_id=context.case_id, mode="ui", verify_status="draft",
                        ui={"page_url": "http://x", "actions": [{"type": "click"}]},
                        assertions={"response": {"status": 200}})

    def runner(exec_spec, context):
        return AgentRuntimeResult(status="PASSED",
                                  actions=[{"action": "click", "target": "#btn"}],
                                  assertions=[{"passed": True}], evidence=[shot])

    def verify(exec_spec, actions, context):
        rec = ReconcileResult(consistent=True, api_total=1, db_total=1, table="t1")
        return {"verdict": "pass",
                "sources": reconcile_to_sources(rec, ui=bool(actions.get("steps"))),
                "reconcile": rec}

    agents = {"spec": SpecAgent(modeler, auto_verify=True),
              "actions": ActionsAgent(runner),
              "evidence": EvidenceAgent(verify)}
    with tempfile.TemporaryDirectory() as directory:
        result = run_case(agents, directory, "TC01")
        assert result.completed and result.stopped_at == ""


def main() -> None:
    test_spec_agent_translates_execspec_and_marks_verified()
    test_spec_agent_default_keeps_draft_and_is_rejected()
    test_actions_agent_backfills_from_spec_and_hashes_evidence()
    test_actions_agent_marks_safety_blocked()
    test_evidence_agent_merges_hashes_and_sources()
    test_full_pipeline_through_real_adapters()
    print("test_stage_adapters ✅ 全部通过")


if __name__ == "__main__":
    main()
