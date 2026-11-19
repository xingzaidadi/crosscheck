from __future__ import annotations

from pathlib import Path

from PIL import Image

from core.arsenal import Capability, execute_plan, plan_dependencies
from core.asset_pipeline import can_execute, candidate_from_capture, create_candidate, promote
from core.case_v2 import migrate_v1, to_legacy_execution, validate_v2
from core.feature_gate import FeatureGate, evaluate
from core.layered_execution import LayerResult, LayerVerdict, aggregate
from core.visual_gate import compare


def test_case_v2_migration_and_validation():
    case = migrate_v1({"schema_version": 1, "case_id": "c1", "title": "t", "suite_id": "s",
                       "status": "draft", "layers": {"required": ["api"]},
                       "actions": [{"capability": "thing.create"}],
                       "assertions": {"api": [{"id": "a1", "subject": "status", "operator": "equals", "expected": "OK"}]}})
    assert validate_v2(case) == []
    assert case["action"]["capability"] == "thing.create"
    projected = to_legacy_execution(case)
    assert projected["execution"]["action_ref"] == "thing.create"


def test_plan_execution_compensates_on_failure():
    capabilities = [Capability("a", "1", "api", {"x": "id"}, environment="test"),
                    Capability("b", "1", "api", {}, environment="test", effects={"mutates": True})]
    plan = plan_dependencies({"case_id": "c", "action": {"capability": "b"},
                              "preconditions": [{"capability": "a"}]}, capabilities,
                             environment="test", run_id="r")
    result = execute_plan(plan, {"a": lambda **_: {"outputs": {"id": "1"}},
                                 "b": lambda **_: (_ for _ in ()).throw(RuntimeError("boom"))})
    assert result["status"] == "failed"
    assert result["compensation"][0]["state"] == "compensated"


def test_layers_assets_feature_gate_and_visual(tmp_path: Path):
    result = aggregate([LayerResult("ui", LayerVerdict.PASS, ["ui.png"]),
                        LayerResult("api", LayerVerdict.ENV_ERROR)], {"ui", "api"})
    assert result["verdict"] == "INCONCLUSIVE"
    asset = create_candidate({"action": "click"})
    for state in ("replay_verified", "human_verified", "approved", "healthy"):
        asset = promote(asset, state, evidence=["capture.json"])
    assert can_execute(asset)
    sanitized = candidate_from_capture({"request": {"password": "hidden", "name": "ok"}})
    assert sanitized["payload"]["request"]["password"] == "{{secret}}"
    gate = evaluate(FeatureGate("f", ("c1", "c2")),
                     [{"case_id": "c1", "verdict": "PASS"}, {"case_id": "c2", "verdict": "PASS"}])
    assert gate["done"]
    ref = tmp_path / "ref.png"
    actual = tmp_path / "actual.png"
    Image.new("RGBA", (2, 2), "white").save(ref)
    Image.new("RGBA", (2, 2), "white").save(actual)
    assert compare(ref, actual)["passed"]


def test_layer_policy_keeps_optional_and_deferred_separate():
    result = aggregate([LayerResult("ui", LayerVerdict.PASS), LayerResult("api", LayerVerdict.FAIL)],
                       {"required": ["ui"], "optional": ["api"], "deferred": ["db"]})
    assert result["verdict"] == "PASS"
    assert result["optional_failures"] == ["api"]
    assert result["deferred"] == ["db"]
