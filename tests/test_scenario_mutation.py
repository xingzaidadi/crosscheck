"""缺陷3 回归:场景动作必须兑现场景意图,靠结构化变换而非散文重拼。

审计问题:empty_query / not_found / reset_filter 只是把场景意图拼进自然语言尾句再
重新解析,导致 not_found 仍沿用基础指令里的真实查询值(例如 1001),"用不存在的数据"
根本没进 actions —— 场景名义上在跑,实际没测到它该测的。

本测试锁死:
  · empty_query  : 查询输入值被清空(value="")。
  · not_found    : 查询输入值被替换为保证不存在的 AUTOTEST_ 值(不再是原值)。
  · reset_filter : 动作里保证存在"查询"触发与"重置"动作。
  · 没有查询输入可变换的场景(empty_query/not_found)→ BLOCKED,不降级假通过。
  · scenario_execution_drafts 的草稿真的带上变换后的动作(端到端接线)。

纯结构化,不依赖 playwright、不访问真实后端。
"""
from types import SimpleNamespace

from core.ui_agent.capabilities import (
    apply_scenario_mutation,
    scenario_execution_drafts,
    _GUARANTEED_ABSENT_VALUE,
)


def _query_actions():
    # 典型查询计划:填一个查询值 + 点查询。
    return [
        {"action": "search_value", "value": "1001", "purpose": "query"},
        {"action": "click", "text": "查询"},
    ]


def _query_inputs(actions):
    return [a for a in actions
            if a.get("purpose") == "query"
            and a.get("action") in ("search_value", "text", "number", "fill")]


def test_empty_query_clears_all_query_values():
    actions, blocked = apply_scenario_mutation("empty_query", _query_actions())
    assert blocked is None
    inputs = _query_inputs(actions)
    assert inputs, "空条件场景应保留查询输入字段(只是置空)"
    assert all(a.get("value") == "" for a in inputs)
    # 查询触发动作仍在:空条件也要真的点一次查询。
    assert any(a.get("action") == "click" and a.get("text") == "查询" for a in actions)


def test_not_found_replaces_value_with_guaranteed_absent():
    actions, blocked = apply_scenario_mutation("not_found", _query_actions())
    assert blocked is None
    inputs = _query_inputs(actions)
    assert inputs
    # 关键:原值 1001 必须被替换,且替换为保证不存在的值,不能还是业务真实值。
    assert all(a.get("value") == _GUARANTEED_ABSENT_VALUE for a in inputs)
    assert all(a.get("value") != "1001" for a in inputs)


def test_reset_filter_guarantees_query_then_reset():
    # 原始计划只有填值,没有查询/重置动作。
    actions, blocked = apply_scenario_mutation(
        "reset_filter", [{"action": "search_value", "value": "x", "purpose": "query"}])
    assert blocked is None
    texts = [a.get("text") for a in actions if a.get("action") == "click"]
    assert "查询" in texts
    assert "重置" in texts


def test_no_query_input_makes_empty_query_blocked():
    # 页面根本没有查询输入(只有一个导航点击)→ 无法构造空条件 → BLOCKED,不假通过。
    actions, blocked = apply_scenario_mutation(
        "empty_query", [{"action": "click", "text": "订单中心"}])
    assert blocked is not None
    assert "空条件" in blocked or "查询输入" in blocked


def test_no_query_input_makes_not_found_blocked():
    actions, blocked = apply_scenario_mutation(
        "not_found", [{"action": "click", "text": "订单中心"}])
    assert blocked is not None


def test_mutation_does_not_touch_original_actions():
    original = _query_actions()
    snapshot = [dict(a) for a in original]
    apply_scenario_mutation("not_found", original)
    assert original == snapshot, "变换必须作用在副本上,不得就地污染入参"


def test_happy_path_keeps_actions_unchanged():
    actions, blocked = apply_scenario_mutation("happy_path", _query_actions())
    assert blocked is None
    assert [a.get("value") for a in _query_inputs(actions)] == ["1001"]


def test_drafts_carry_mutated_actions_end_to_end():
    # 端到端:基础指令含真实查询值,not_found 草稿的动作里不得再出现该真实值,
    # 必须是 AUTOTEST_ 不存在值。证明 scenario_execution_drafts 走的是结构化变换。
    request = SimpleNamespace(
        url="http://example.test/orders",
        instruction="在订单中心输入订单号 1001 并查询,然后查看第一条记录的详情",
        role="default",
    )
    drafts = scenario_execution_drafts(request)
    not_found = next((d for d in drafts if d.get("scenario") == "not_found"), None)
    assert not_found is not None, "应生成 not_found 场景草稿"
    # 若页面建模出查询输入,则 not_found 应为可执行 draft 且值被替换;
    # 若未建出查询输入,则应为 blocked —— 两种都不得保留原值 1001 假装测过。
    if not_found.get("state") == "draft":
        values = [a.get("value") for a in not_found.get("actions") or []
                  if a.get("purpose") == "query"]
        assert values, "not_found draft 应含查询输入动作"
        assert all(v == _GUARANTEED_ABSENT_VALUE for v in values)
        assert "1001" not in values
    else:
        assert not_found.get("state") == "blocked"
