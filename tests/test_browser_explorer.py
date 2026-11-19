from core.browser_explorer import explore_task
from core.exploration_actions import build_action_candidates, extract_safe_labels


def test_explorer_refuses_unsafe_task_without_launching_browser(tmp_path):
    result = explore_task(
        {"safe_to_auto_explore": False, "page_url": "https://example.test", "text": "提交"},
        workspace=tmp_path,
        output=tmp_path / "out",
    )
    assert result["status"] == "WAITING_FOR_INPUT"


def test_explorer_requires_page_url(tmp_path):
    result = explore_task(
        {"safe_to_auto_explore": True, "page_url": ""},
        workspace=tmp_path,
        output=tmp_path / "out",
    )
    assert result["status"] == "WAITING_FOR_INPUT"


def test_action_candidates_only_include_safe_read_only_labels():
    assert extract_safe_labels("点击明细查询，再查看详情并提交") == ["明细查询", "详情"]
    candidates = build_action_candidates("点击明细查询", "需求列表 明细查询")
    assert candidates == [{"action": "click", "text": "明细查询", "visible": True,
                           "state": "candidate", "requires_replay": True}]
