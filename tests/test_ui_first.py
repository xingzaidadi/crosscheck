from pathlib import Path
import json

from core.suite_plan import build_suite_plan
from core.ui_first import ui_readiness, ui_verdict
from core.interfaces import CaseResult, Verdict
from run_batch import finalize_result
from core import ui_check
from core.ui_check import _semantic_replay_layer
from scripts.ui_first_readiness import main as ui_first_readiness_main


class Raw:
    case_id = "TC1"
    name = "页面上传文件"
    category = "附件"
    module = "附件"
    level = "P0"
    tags = ""
    preconditions = ""
    notes = ""
    steps_text = "页面点击上传"
    expected_text = "页面显示文件"


class Spec:
    case_id = "TC1"
    verify_status = "human_verified"
    mode = "ui"
    ui = {"page_url": "/upload"}
    request = None
    assertions = {}
    db = ""
    feature = "upload"
    blocked = ""
    needs_review = []
    raw = {}


def test_ui_phase_does_not_require_api_or_db():
    plan = build_suite_plan([Raw()], [Spec()], phase="ui")
    assert plan["executable"] == 1
    assert plan["cases"][0]["phase_required_layers"] == ["ui"]


def test_ui_readiness_and_verdict_keep_future_layers_explicit():
    readiness = ui_readiness({}, ["ui"], approved=True)
    assert readiness["executable"]
    result = ui_verdict(True)
    assert result == {"verdict": "UI_PASS", "ui": "PASS", "api": "NOT_COVERED",
                      "db": "NOT_COVERED", "cross_verdict": "NOT_EVALUATED"}


def test_ui_phase_result_is_attached_to_real_case_result():
    result = finalize_result(Spec(), CaseResult("TC1", Verdict.PASS, report={"layers": [
        {"name": "UI 操作回放", "ok": True},
    ]}), phase="ui")
    assert result.phase_verdict == "UI_PASS"
    assert result.report["phase_result"]["db"] == "NOT_COVERED"


def test_optional_db_failure_does_not_overwrite_ui_pass():
    result = finalize_result(Spec(), CaseResult("TC1", Verdict.FAIL, report={"layers": [
        {"name": "页面 ↔ 接口 渲染校验", "ok": True},
        {"name": "接口 ↔ 库 对账", "ok": False},
    ]}), phase="ui")
    assert result.phase_verdict == "UI_PASS"
    assert result.report["phase_result"]["db"] == "OPTIONAL"
    assert result.report["phase_result"]["deferred_layers"] == ["api", "db"]
    assert result.verdict is Verdict.PASS


def test_ui_only_pass_clears_failure_from_deferred_db_layer():
    result = finalize_result(Spec(), CaseResult("TC1", Verdict.FAIL, failure_class="TARGET_FAIL", report={
        "layers": [
            {"name": "页面 ↔ 接口 渲染校验", "ok": True},
            {"name": "接口 ↔ 库 对账", "ok": False},
        ],
    }), phase="ui")
    assert result.verdict is Verdict.PASS
    assert result.failure_class == ""
    assert result.report["phase_result"]["deferred_layers"] == ["api", "db"]


def test_ui_runner_does_not_open_or_reconcile_db_in_ui_phase(monkeypatch):
    called = []

    def fail_reconcile(*args, **kwargs):
        called.append("reconcile")
        raise AssertionError("UI-only phase must not reconcile DB")

    monkeypatch.setattr(ui_check, "Reconciler", fail_reconcile)
    assert ui_check.run_ui_spec.__kwdefaults__["phase"] == "all"
    assert called == []


def test_failed_semantic_action_cannot_pass_ui_case():
    ok, layer = _semantic_replay_layer([
        {"action": "click", "target": "执行中", "ok": False, "error": "not found"}
    ])
    assert not ok
    assert layer["ok"] is False


def test_ui_first_readiness_uses_reviewed_suite_local_binding(tmp_path, monkeypatch):
    suite_dir = tmp_path / "suite"
    (suite_dir / "cases").mkdir(parents=True)
    (suite_dir / "ui_bindings").mkdir()
    (suite_dir / "suite.yaml").write_text(
        "schema_version: 1\nsuite_id: demo\n", encoding="utf-8"
    )
    (suite_dir / "cases" / "case.yaml").write_text(
        """schema_version: 1
case_id: demo/TC1
title: Read-only case
suite_id: demo
version: '1.0'
source:
  case_key: TC1
priority: P1
status: draft
layers:
  required: [ui]
actions: {ui: []}
assertions: {ui: []}
approval: {status: draft}
""",
        encoding="utf-8",
    )
    (suite_dir / "ui_bindings" / "TC1.yaml").write_text(
        "case_id: TC1\nmode: ui\nverify_status: human_verified\nui:\n  page_url: /demo\n",
        encoding="utf-8",
    )
    output = tmp_path / "readiness.json"
    monkeypatch.setattr(
        "sys.argv",
        ["ui_first_readiness", "--suite", str(suite_dir), "--output", str(output)],
    )
    assert ui_first_readiness_main() == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["counts"] == {"UI_EXECUTABLE": 1}


def test_ui_first_readiness_blocks_unhealthy_binding(tmp_path, monkeypatch):
    suite_dir = tmp_path / "suite"
    (suite_dir / "cases").mkdir(parents=True)
    (suite_dir / "ui_bindings").mkdir()
    (suite_dir / "suite.yaml").write_text(
        "schema_version: 1\nsuite_id: demo\n", encoding="utf-8"
    )
    case = {
        "schema_version": 1,
        "case_id": "demo/TC1",
        "title": "Read-only case",
        "suite_id": "demo",
        "version": "1.0",
        "source": {"case_key": "TC1"},
        "priority": "P1",
        "status": "draft",
        "layers": {"required": ["ui"]},
        "actions": {"ui": []},
        "assertions": {"ui": []},
        "approval": {"status": "draft"},
    }
    import yaml
    (suite_dir / "cases" / "case.yaml").write_text(
        yaml.safe_dump(case), encoding="utf-8"
    )
    (suite_dir / "ui_bindings" / "TC1.yaml").write_text(
        "case_id: TC1\nmode: ui\nverify_status: human_verified\nbinding_health: stale_route\nui:\n  page_url: /demo\n",
        encoding="utf-8",
    )
    output = tmp_path / "readiness.json"
    monkeypatch.setattr(
        "sys.argv",
        ["ui_first_readiness", "--suite", str(suite_dir), "--output", str(output)],
    )
    assert ui_first_readiness_main() == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["counts"] == {"UI_BLOCKED": 1}
