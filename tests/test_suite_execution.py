from pathlib import Path

import yaml

from core.spec import dump_spec, ExecSpec
from core.suite_context import SuiteContext
from core.suite_execution import build_execution_plan


def canonical_case(case_key="TC01"):
    return {
        "schema_version": 1,
        "case_id": f"demo/{case_key}-1",
        "title": "按钮展示",
        "suite_id": "demo",
        "source": {"case_key": case_key},
        "priority": "P0",
        "status": "draft",
        "layers": {"required": ["ui", "api"]},
        "actions": {"ui": [], "api": [], "db": []},
        "assertions": {"ui": [], "api": [], "db": []},
        "cleanup": {"targets": []},
        "approval": {"status": "draft", "content_hash": ""},
        "execution": {},
    }


def test_reviewed_binding_is_selected_by_canonical_source_key(tmp_path):
    workspace = tmp_path / "workspace"
    suite_dir = workspace / "suites" / "demo"
    (suite_dir / "cases").mkdir(parents=True)
    (suite_dir / "ui_bindings").mkdir()
    suite = {"schema_version": 1, "suite_id": "demo", "environment": "test"}
    case = canonical_case()
    (suite_dir / "suite.yaml").write_text(yaml.safe_dump(suite), encoding="utf-8")
    dump_spec(ExecSpec(
        case_id="TC01-UI", title="按钮展示", mode="ui", kind="query",
        verify_status="human_verified", ui={"page_url": "https://example.test"},
    ), suite_dir / "ui_bindings" / "TC01.yaml")

    specs, report = build_execution_plan(
        suite, [case], SuiteContext.create(suite_dir, workspace), suite_dir,
    )

    assert specs == []
    assert report["counts"] == {"ASSERTION_REQUIRED": 1}
    assert report["execution_ready_rate"] == 0.0
    assert report["full_coverage_ready"] == 0
    assert report["cases"][0]["missing_layers"] == ["api"]
    assert report["cases"][0]["full_coverage_ready"] is False
    assert "api_binding" in report["cases"][0]["readiness_gaps"]
    assert "semantic_actions" in report["cases"][0]["readiness_gaps"]
    assert "ui_oracle" in report["cases"][0]["readiness_gaps"]
    assert "replay_required" in report["cases"][0]["readiness_gaps"]


def test_unbound_case_is_reported_once(tmp_path):
    suite_dir = tmp_path / "suite"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    suite_dir = workspace / "suites" / "demo"
    suite_dir.mkdir(parents=True)
    (suite_dir / "suite.yaml").write_text(yaml.safe_dump({
        "schema_version": 1, "suite_id": "demo", "environment": "test",
    }), encoding="utf-8")
    suite = {"schema_version": 1, "suite_id": "demo", "environment": "test"}

    specs, report = build_execution_plan(
        suite, [canonical_case()], SuiteContext.create(suite_dir, workspace), suite_dir,
    )

    assert specs == []
    assert report["counts"] == {"BINDING_REQUIRED": 1}
    assert report["execution_ready_rate"] == 0.0
    assert report["gap_counts"]["page_entry"] == 1
    assert report["gap_counts"]["spec_approval"] == 1
