"""缺陷1 回归:整体状态必须聚合全部必测场景,不能只读 happy_path。

审计实测反例:主流程 PASSED、空条件 PASSED、不存在数据 FAILED、重置 BLOCKED,
旧逻辑总报告仍 PASSED。本测试锁死:只要有必测场景红/未完成,整体不得 PASSED。
"""
from scripts.agent_test import aggregate_scenario_status


def _matrix(*verdicts):
    return {"scenarios": [{"scenario": f"s{i}", "verdict": v} for i, v in enumerate(verdicts)]}


def test_audit_reproduction_not_all_green_must_not_pass():
    # 审计原样:happy/empty 绿,not_found 红,reset 阻塞
    matrix = _matrix("PASSED", "PASSED", "FAILED", "BLOCKED")
    assert aggregate_scenario_status(matrix) == "FAILED"


def test_any_failed_scenario_makes_overall_failed():
    assert aggregate_scenario_status(_matrix("PASSED", "FAILED")) == "FAILED"
    assert aggregate_scenario_status(_matrix("PASSED", "DRAFT_FAILED")) == "FAILED"
    assert aggregate_scenario_status(_matrix("PASSED", "ENV_ERROR")) == "FAILED"


def test_blocked_or_inconclusive_makes_overall_partial_not_passed():
    assert aggregate_scenario_status(_matrix("PASSED", "BLOCKED")) == "PARTIAL"
    assert aggregate_scenario_status(_matrix("PASSED", "INCONCLUSIVE")) == "PARTIAL"
    assert aggregate_scenario_status(_matrix("PASSED", "SKIPPED_NEEDS_AUTH")) == "PARTIAL"
    assert aggregate_scenario_status(_matrix("PASSED", "SKIPPED_UNKNOWN_STATE")) == "PARTIAL"


def test_all_green_passes():
    assert aggregate_scenario_status(_matrix("PASSED", "PASSED", "PASSED")) == "PASSED"
    assert aggregate_scenario_status(_matrix("PASSED")) == "PASSED"


def test_empty_matrix_is_inconclusive_not_passed():
    assert aggregate_scenario_status({"scenarios": []}) == "INCONCLUSIVE"
    assert aggregate_scenario_status({}) == "INCONCLUSIVE"


def test_failed_dominates_blocked():
    # 同时有 FAILED 和 BLOCKED 时,FAILED 优先(更严重)
    assert aggregate_scenario_status(_matrix("FAILED", "BLOCKED", "PASSED")) == "FAILED"
