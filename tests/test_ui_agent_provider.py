from core.ui_agent.planner import ObservationPlanner
from core.ui_agent.provider import normalize_proposal


def test_planner_accepts_safe_workspace_provider():
    planner = ObservationPlanner("打开订单详情", [{"action": "click", "text": "订单详情"}],
                                resolver=lambda **_: {"action": {"action": "click", "text": "订单中心"}})
    decision = planner.decide({"body_text": "", "controls": [
        {"tag": "button", "text": "订单中心", "role": "button", "disabled": False}
    ]})
    assert decision.kind == "explore"
    assert decision.action["text"] == "订单中心"


def test_planner_accepts_provider_form_action_when_field_is_observed():
    planner = ObservationPlanner(
        "查询订单",
        [{"action": "text", "label": "订单号", "value": "1001", "purpose": "query"}],
        resolver=lambda **_: {"action": {"action": "text", "label": "订单号", "value": "1001",
                                           "purpose": "query"}},
    )
    decision = planner.decide({"body_text": "", "controls": [], "fields": [
        {"label": "订单号", "name": "orderNo", "readonly": False},
    ]})
    assert decision.kind == "execute"
    assert decision.action["action"] == "text"


def test_provider_cannot_return_selector_or_javascript():
    planner = ObservationPlanner(
        "打开订单详情",
        [{"action": "click", "text": "订单详情"}],
        resolver=lambda **_: {"action": {"action": "click", "text": "订单详情", "selector": "body"}},
    )
    decision = planner.decide({"body_text": "", "controls": [], "fields": []})
    assert decision.kind == "blocked"


def test_provider_response_is_normalized_to_a_small_safe_json_contract():
    assert normalize_proposal({
        "action": {"action": "click", "text": "订单中心"},
        "confidence": 4,
        "reason": "visible semantic gateway",
    }) == {
        "action": {"action": "click", "text": "订单中心"},
        "confidence": 1.0,
        "reason": "visible semantic gateway",
    }
    assert normalize_proposal({
        "action": {"action": "click", "text": "订单中心", "javascript": "alert(1)"},
    }) == {}


class PlannerObject:
    def plan(self, **context):
        return {"action": {"action": "click", "text": "订单中心"}, "confidence": 0.8}


def test_provider_object_with_plan_method_is_supported():
    planner = ObservationPlanner("打开订单详情", [{"action": "click", "text": "订单详情"}],
                                resolver=PlannerObject())
    decision = planner.decide({"body_text": "", "controls": [
        {"tag": "button", "text": "订单中心", "role": "button", "disabled": False},
    ], "fields": []})
    assert decision.kind == "explore"
    assert decision.action["text"] == "订单中心"
