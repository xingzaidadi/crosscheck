from core.ui_agent.recovery import recover_and_click
from core.ui_agent.risk_policy import assess_action
from core.ui_agent.verifier import enrich_oracles
from core.ui_agent.planner import ObservationPlanner
from core.agent_test_intake import AgentTestRequest, build_agent_plan
from core.ui_agent.runtime import AgentRuntime


class Locator:
    def __init__(self, count=0, fail=False):
        self._count = count
        self._fail = fail
        self.first = self

    def count(self):
        return self._count

    def scroll_into_view_if_needed(self, **kwargs):
        return None

    def click(self, **kwargs):
        if self._fail:
            raise RuntimeError("covered")


class Page:
    def __init__(self):
        self.calls = 0

    def get_by_role(self, *args, **kwargs):
        self.calls += 1
        return Locator(1, fail=self.calls == 1)

    def get_by_text(self, *args, **kwargs):
        return Locator(1)

    def locator(self, *args, **kwargs):
        return Locator(0)


def test_recovery_switches_locator_strategy_after_failure():
    result = recover_and_click(Page(), "订单管理")
    assert result["ok"] is True
    assert len(result["events"]) >= 2


def test_risk_policy_blocks_write_and_destructive_actions():
    assert assess_action({"action": "click", "text": "查询"}, policy="read_only").allowed
    assert assess_action({"action": "select", "label": "状态筛选", "value": "处理中"}, policy="read_only").allowed
    assert not assess_action({"action": "fill", "label": "备注", "value": "changed"}, policy="read_only").allowed
    assert not assess_action({"action": "click", "text": "提交"}, policy="read_only").allowed
    decision = assess_action({"action": "click", "text": "删除"}, policy="authorized_write",
                             allow_write=True, write_scope="测试订单")
    assert decision.level == "destructive" and not decision.allowed


def test_semantic_readonly_assertion_is_generated():
    result = enrich_oracles([], "打开详情并确认页面只读")
    assert result[0]["kind"] == "readonly"


def test_observation_planner_replans_through_safe_gateway():
    planner = ObservationPlanner("打开订单详情", [{"action": "click", "text": "订单详情"}])
    first = planner.decide({"body_text": "订单管理", "controls": [
        {"tag": "button", "text": "订单管理", "role": "", "disabled": False}
    ]})
    assert first.kind == "explore"
    assert first.action["text"] == "订单管理"
    planner.mark_success(first)
    second = planner.decide({"body_text": "订单详情", "controls": [
        {"tag": "button", "text": "订单详情", "role": "", "disabled": False}
    ]})
    assert second.kind == "execute"
    assert second.action["text"] == "订单详情"


def test_observation_planner_reaches_high_level_goal_through_visible_gateway():
    planner = ObservationPlanner("测试订单中心", [{"action": "reach", "target": "订单中心"}])
    decision = planner.decide({"body_text": "工作台", "controls": [
        {"tag": "button", "text": "订单中心", "role": "button", "disabled": False}
    ]})
    assert decision.kind == "execute"
    assert decision.action == {"action": "click", "text": "订单中心"}


def test_observation_planner_fills_query_value_before_query_click():
    planner = ObservationPlanner(
        "查询订单1001",
        [{"action": "search_value", "value": "1001", "purpose": "query"},
         {"action": "click", "text": "查询"}],
    )
    decision = planner.decide({"body_text": "订单列表 查询", "fields": [
        {"label": "订单号", "name": "", "disabled": False, "readonly": False}
    ], "controls": [{"text": "查询", "tag": "button", "disabled": False}]})
    assert decision.action == {"action": "text", "label": "订单号", "value": "1001", "purpose": "query"}


def test_blocked_runtime_still_captures_final_quality_evidence(tmp_path):
    html = tmp_path / "blocked.html"
    html.write_text("<button>订单中心</button><h1>工作台</h1>", encoding="utf-8")
    plan = build_agent_plan(AgentTestRequest(
        url=html.as_uri(), instruction="打开第一条订单记录并确认详情页只读"
    ))
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        result = AgentRuntime(max_steps=3).run(page, plan, tmp_path / "evidence")
        browser.close()
    assert result.status in {"BLOCKED", "FAILED"}
    assert result.observations
    assert result.accessibility
    assert result.quality
    assert (tmp_path / "evidence" / "after.png").is_file()
