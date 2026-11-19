from pathlib import Path

import yaml

from core.suite_context import SuiteContext
from core.suite_execution import build_execution_plan
from core.suite_execution import canonical_assertion_requirements


def test_ui_first_ignores_cross_layer_block_but_keeps_ui_binding(tmp_path: Path):
    workspace = tmp_path / "workspace"
    suite_dir = workspace / "suites" / "demo"
    (suite_dir / "cases").mkdir(parents=True)
    (suite_dir / "ui_bindings").mkdir()
    suite = {"schema_version": 1, "suite_id": "demo", "environment": "test",
             "authorization": {"confirmed_non_production": True}}
    case = {"schema_version": 1, "case_id": "demo/TC1-1", "title": "UI list", "suite_id": "demo",
            "status": "draft", "priority": "P1", "source": {"case_key": "TC1"},
            "layers": {"required": ["ui", "db"]}, "data": {"preconditions_text": ""},
            "actions": {"source_text": "open list", "ui": []},
            "assertions": {"source_text": "list visible", "ui": []}, "approval": {},
            "execution": {"blocked": "DB oracle is incomplete"}}
    binding = {"case_id": "TC1", "mode": "ui", "verify_status": "human_verified",
               "ui": {"page_url": "https://example.invalid/list",
                      "actions": [{"click": {"selector": "text=List"}}],
                      "visibility_asserts": [{"selector": "text=Items"}]},
               "raw": {"binding_health": "db_oracle_incomplete"}}
    (suite_dir / "suite.yaml").write_text(yaml.safe_dump(suite), encoding="utf-8")
    (suite_dir / "cases" / "TC1.yaml").write_text(yaml.safe_dump(case), encoding="utf-8")
    (suite_dir / "ui_bindings" / "TC1.yaml").write_text(yaml.safe_dump(binding), encoding="utf-8")
    context = SuiteContext.create(suite_dir, workspace)
    specs, report = build_execution_plan(suite, [case], context, suite_dir, phase="ui")
    assert [spec.case_id for spec in specs] == ["TC1"]
    assert report["phase"] == "ui"
    assert report["cases"][0]["execution_ready"] is True


def test_canonical_source_expectations_become_required_assertions():
    case = {
        "source": {"case_key": "TC7"},
        "assertions": {"source_text": "1. 页面显示订单\n2. 状态为已提交"},
    }
    identifiers, texts = canonical_assertion_requirements(case)
    assert identifiers == ["TC7:expected:1", "TC7:expected:2"]
    assert texts[identifiers[0]] == "页面显示订单"
    assert texts[identifiers[1]] == "状态为已提交"
