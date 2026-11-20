from core.case_orchestration import build_case_plans, coverage_report
from core.case_source import RawCase


def test_case_plan_is_built_from_case_and_keeps_traceability():
    cases = [RawCase(name="TC01 查询订单", level="P0", module="订单/查询", row=7,
                     steps_text="查询订单", expected_text="显示“订单列表”")]
    plans = build_case_plans(cases, "https://example.test")
    assert plans[0].case_id == "TC01"
    assert plans[0].source_row == 7
    assert plans[0].plan["oracles"]


def test_coverage_report_does_not_count_unexecuted_cases_as_passed():
    cases = [RawCase(name="TC01 查询", steps_text="查询")]
    plans = build_case_plans(cases, "https://example.test")
    report = coverage_report(plans)
    assert report["not_covered"] == ["TC01"]
    assert report["status_counts"] == {"PLANNED": 1}


def test_supporting_material_can_reveal_missing_case_dimensions():
    cases = [RawCase(name="TC01 查询", steps_text="查询订单")]
    plans = build_case_plans(cases, "https://example.test")
    manifest = {"sources": [{"signals": ["authorization", "database"]}]}
    report = coverage_report(plans, source_manifest=manifest)
    signals = {item["signal"] for item in report["evidence_analysis"]["potential_case_gaps"]}
    assert signals == {"authorization", "database"}
