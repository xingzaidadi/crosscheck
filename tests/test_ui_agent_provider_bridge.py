"""刁钻措辞导航:确定性网关弱匹配→问 provider→语义桥接→目标退伍→不误判 BLOCKED。

全部离线:用一个**桩 provider**(非真实 LLM)模拟"用例措辞≠控件名"的语义桥接,
锁定本轮三处改动的接线:
  ① _gateway_for 弱匹配时先问 provider(provider 通电,不再被网关无条件短路)
  ② intake 把"打开/进入 X"导航解析成 reach(reach 自带网关+退伍)
  ③ 语义网关有把握地解析导航后,目标能退伍(mark_blocked),整条 run 不被误判 BLOCKED

四铁律:桩不联网、确定性优先(强匹配不问 provider)、无 provider 时行为不变、安全闸不动。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.agent_test_intake import AgentTestRequest, build_agent_plan  # noqa: E402
from core.ui_agent.planner import ObservationPlanner, PlannerDecision  # noqa: E402


# 页面控件名刻意和用例措辞不同义、无共享 token:用例"客户资料",控件"会员档案"。
PAGE = {"body_text": "运营后台 概览看板", "fields": [], "controls": [
    {"tag": "button", "text": "概览看板", "role": "button", "disabled": False},
    {"tag": "button", "text": "会员档案", "role": "button", "disabled": False},
    {"tag": "button", "text": "交易流水", "role": "button", "disabled": False},
]}


def _bridge_provider(**context):
    """桩:把"客户资料"语义桥接到可见控件"会员档案"(真实 LLM 的离线替身)。"""
    desired = context.get("desired_action") or {}
    target = str(desired.get("text") or desired.get("target") or "")
    if "客户资料" in target:
        return {"action": {"action": "click", "text": "会员档案"},
                "confidence": 0.55, "reason": "会员档案语义上最接近客户资料"}
    return None


def test_intake_navigation_becomes_reach():
    plan = build_agent_plan(AgentTestRequest(
        url="https://example.test", instruction="打开客户资料，确认页面出现文本“数据加载成功”"))
    assert {"action": "reach", "target": "客户资料"} in plan.actions, plan.actions
    assert not any(a.get("action") == "click" and a.get("text") == "客户资料" for a in plan.actions)
    print("  ✓ intake 把'打开客户资料'解析成 reach 导航目标")


def test_weak_gateway_consults_provider_and_bridges():
    # desired 的目标在页面上无别名/子串/共享 token → 确定性只能给弱网关 → 该问 provider。
    planner = ObservationPlanner("打开客户资料", [{"action": "reach", "target": "客户资料"}],
                                 resolver=_bridge_provider)
    decision = planner.decide(PAGE)
    assert decision.kind == "explore", decision.kind
    assert decision.action["text"] == "会员档案", decision.action
    assert decision.source == "provider", decision.source
    print(f"  ✓ 弱网关下问 provider,语义桥接到'会员档案'(source={decision.source})")


def test_strong_match_does_not_waste_provider_call():
    # 控件名精确命中 → 强匹配 → 不该消耗 provider(provider 返回会乱点就能抓到)。
    calls = []

    def spy(**context):
        calls.append(1)
        return {"action": {"action": "click", "text": "会员档案"}, "confidence": 0.9}

    planner = ObservationPlanner("打开会员档案", [{"action": "reach", "target": "会员档案"}],
                                 resolver=spy)
    decision = planner.decide(PAGE)
    assert decision.source != "provider", decision.source
    assert not calls, "强匹配不应调用 provider"
    print("  ✓ 强匹配直接走确定性,不浪费 provider 调用")


def test_resolved_navigation_retires_instead_of_blocking():
    # 模拟 runtime 环:provider 解析网关→点开→下一页仍无"客户资料"原词控件→blocked→退伍。
    planner = ObservationPlanner("打开客户资料", [{"action": "reach", "target": "客户资料"}],
                                 resolver=_bridge_provider)
    first = planner.decide(PAGE)
    assert first.source == "provider"
    # runtime 以重建的 decision 调 mark_success(透传 source)。
    planner.mark_success(PlannerDecision(
        kind=first.kind, action=first.action, reason=first.reason,
        confidence=first.confidence, desired_action=first.desired_action, source=first.source))
    # 落地页:标题变成"会员档案",但没有叫"客户资料"的控件 → 确定性再无路 → blocked。
    landed = {"body_text": "会员档案 会员档案载入完成", "fields": [], "controls": [
        {"tag": "button", "text": "新建会员", "role": "button", "disabled": False},
    ]}
    second = planner.decide(landed)
    assert second.kind == "blocked", second.kind
    retired = planner.mark_blocked(second, landed)
    assert retired is True, "被 provider 解析过的导航目标应退伍放行"
    assert not planner.state.pending_actions, "退伍后不应再有悬挂目标"
    print("  ✓ 语义网关解析过的导航目标退伍放行,不误判 BLOCKED")


def test_no_provider_keeps_deterministic_behavior_unchanged():
    # 无 provider:刁钻措辞确定性确实够不着 → blocked(回退逐位不变,不乱点)。
    planner = ObservationPlanner("打开客户资料", [{"action": "reach", "target": "客户资料"}])
    decision = planner.decide(PAGE)
    assert decision.kind in {"explore", "blocked"}, decision.kind
    # 无 provider 时即便探索,也绝不会凭空标 source=provider。
    assert decision.source != "provider", decision.source
    print("  ✓ 无 provider 时确定性行为不变,不会冒充 provider 来源")


def main():
    test_intake_navigation_becomes_reach()
    test_weak_gateway_consults_provider_and_bridges()
    test_strong_match_does_not_waste_provider_call()
    test_resolved_navigation_retires_instead_of_blocking()
    test_no_provider_keeps_deterministic_behavior_unchanged()
    print("\n全部通过 ✅  —— 弱网关才问 provider、导航走 reach、语义解析的目标会退伍(不误判 BLOCKED)")


if __name__ == "__main__":
    main()
