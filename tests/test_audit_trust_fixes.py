"""审计三条可信性缺陷的离线回归测试(第一档修复的守门测试)。

把外部审计发现的三个"误判/误通过" bug 固化成回归用例,防止再犯:
  - #3  field_text_equals 取不到目标字段值 → 旧逻辑退回全文搜索凑通过;
        修后判 inconclusive(ok=None),绝不拿页面别处的字样冒充目标字段相等。
  - #2a reach 目标名出现在 body_text → 旧逻辑只 observe(不点击)当"已到达";
        修后无真导航证据(resolved_navigations)时必须点可见导航控件,正文里有这串字
        既不短路成"到达"、也不在 mark_blocked 退伍。
  - #2b "是否X"/"X是否正常" → 旧正则把"是"当等号,抽出伪字段断言;修后抽不出断言。

全部离线、零浏览器:#3 用一个最小 fake page 复刻 Playwright 定位 API,
不依赖 chromium;#2a/#2b 是纯逻辑。run_tests.py 把本文件当脚本跑(main+assert)。

跑:python tests/test_audit_trust_fixes.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.ui_test import _evaluate_oracle  # noqa: E402
from core.agent_test_intake import _natural_language_oracles  # noqa: E402
from core.ui_agent.planner import ObservationPlanner, PlannerDecision  # noqa: E402


# --------------------------------------------------------------------------
# 最小 fake page:只实现 field_text_equals 分支用到的 Playwright 定位 API。
# 语义约定:
#   - fields: {label: value}  页面上"标签→可定位到的字段值"(真能取到的目标字段)
#   - body:   全页正文文本(页面别处可能出现 expected 字样,用来诱发旧的全文回退误通过)
# get_by_text(label, exact=True) 命中 fields 里的 label 才算"定位到目标字段"。
# --------------------------------------------------------------------------
class _FakeControl:
    def __init__(self, value):
        self._value = value

    @property
    def first(self):
        return self

    def count(self):
        return 1 if self._value is not None else 0

    def input_value(self):
        return self._value


class _FakeScope:
    def __init__(self, label, value):
        self._label = label
        self._value = value

    def count(self):
        return 1

    def locator(self, selector):
        # 返回字段控件;input_value() 给出目标字段真实值
        return _FakeControl(self._value)

    def inner_text(self):
        return f"{self._label}{self._value}"


class _FakeLabelLocator:
    def __init__(self, label, fields):
        self._label = label
        self._fields = fields

    @property
    def first(self):
        return self

    def count(self):
        return 1 if self._label in self._fields else 0

    def locator(self, selector):
        return _FakeScope(self._label, self._fields[self._label])


class _FakeBody:
    def __init__(self, body):
        self._body = body

    def inner_text(self, *a, **k):
        return self._body


class _FakePage:
    def __init__(self, fields: dict, body: str):
        self._fields = fields
        self._body = body
        self.url = "https://example.test/detail"

    def get_by_text(self, label, exact=True):
        return _FakeLabelLocator(label, self._fields)

    def locator(self, selector):
        if selector == "body":
            return _FakeBody(self._body)
        raise AssertionError(f"未预期的 locator: {selector}")


def test_bug3_field_not_found_is_inconclusive_not_false_pass():
    """#3 核心回归:目标字段 Status 取不到值,但页面别处出现 'Pending' 字样。
    旧逻辑会 `expected in body` → actual='Pending' → 误通过;修后必须判 inconclusive。"""
    # 页面上根本没有名为 'Status' 的可定位字段,但正文里别处出现了 'Pending'
    page = _FakePage(fields={"订单号": "SO-1"}, body="订单号 SO-1 当前状态 Pending 其它说明")
    result = _evaluate_oracle(page, {"kind": "field_text_equals", "value": "Status",
                                     "expected": "Pending"})
    assert result["passed"] is None, f"取不到目标字段必须 inconclusive(None),实得 {result['passed']}"
    print("    ✓ #3 目标字段取不到值 → inconclusive(None),不拿全文里的 Pending 凑通过")


def test_bug3_wrong_field_value_fails_not_passes():
    """#3 延伸:目标字段 Status 真实值是 Draft(≠期望 Pending),哪怕正文别处有 Pending,
    也必须判定为 **不通过**(False),不能被全文命中救成通过。"""
    page = _FakePage(fields={"Status": "Draft"}, body="标题 Status Draft 页脚提示 Pending 审批中")
    result = _evaluate_oracle(page, {"kind": "field_text_equals", "value": "Status",
                                     "expected": "Pending"})
    assert result["passed"] is False, f"目标字段真实值≠期望应判 False,实得 {result['passed']}"
    assert result["actual"] == "Draft", result["actual"]
    print("    ✓ #3 目标字段真实值 Draft≠期望 Pending → False(不被正文里的 Pending 救通过)")


def test_bug3_real_field_match_still_passes():
    """#3 不误伤:目标字段真能取到且等于期望 → 照常通过(修复没把正确通过也杀掉)。"""
    page = _FakePage(fields={"Status": "Pending"}, body="Status Pending")
    result = _evaluate_oracle(page, {"kind": "field_text_equals", "value": "Status",
                                     "expected": "Pending"})
    assert result["passed"] is True, result["passed"]
    print("    ✓ #3 目标字段真实值==期望 → 仍正常通过(不误伤合法通过)")


def test_bug2b_shifou_normal_extracts_no_assertion():
    """#2b 核心回归:'测试订单中心是否正常' 不应抽出任何字段断言(断言数=0)。"""
    oracles = _natural_language_oracles("测试订单中心是否正常")
    assert oracles == [], f"'是否正常' 不应抽出伪断言,实得 {oracles}"
    print("    ✓ #2b '测试订单中心是否正常' 抽出断言数=0(不再把'是'当等号)")


def test_bug2b_more_shifou_variants_extract_nothing():
    """#2b 延伸:多种'是否X'措辞都不抽断言。"""
    for text in ("确认页面是否正确", "检查列表是否可用", "验证支付是否成功"):
        oracles = _natural_language_oracles(text)
        assert oracles == [], f"{text!r} 不应抽出断言,实得 {oracles}"
    print("    ✓ #2b '是否正确/是否可用/是否成功' 等问句一律抽出断言数=0")


def test_bug2b_real_equals_assertion_still_extracted():
    """#2b 不误伤:真正的'字段=值'断言仍能抽出(用'为/等于',非'是否')。"""
    oracles = _natural_language_oracles("确认状态为已完成")
    assert any(o["value"] == "状态" and o["expected"] == "已完成" for o in oracles), oracles
    print("    ✓ #2b 真断言'状态为已完成'仍正常抽出(不误伤合法断言)")


def test_bug2a_menu_name_in_body_is_not_arrival():
    """#2a 核心回归:目标名只出现在 body_text、页面无对应可点导航控件时,
    planner 不得把它短路成 observe('已到达'),也不得在 mark_blocked 退伍放行。"""
    planner = ObservationPlanner("打开订单中心", [{"action": "reach", "target": "订单中心"}])
    # 页面正文里有"订单中心"四个字(如面包屑/说明文案),但没有名为"订单中心"的可点控件
    obs = {"body_text": "欢迎来到订单中心的介绍页", "controls": [
        {"tag": "button", "text": "返回首页", "role": "button", "disabled": False},
    ], "fields": []}
    decision = planner.decide(obs)
    assert not (decision.kind == "execute" and decision.action
                and decision.action.get("action") == "observe"), \
        f"正文里有菜单名不等于到达,不应短路成 observe:{decision.to_dict()}"
    # 且不得凭正文命中退伍放行(mark_blocked 不再认 body_text 短路)
    retired = planner.mark_blocked(
        PlannerDecision("blocked", None, "no path", .9,
                        desired_action={"action": "reach", "target": "订单中心"}),
        obs)
    assert retired is False, "无真导航证据时,reach 目标不应凭正文命中退伍放行"
    assert planner.state.pending_actions, "目标不应被凭空消费"
    print("    ✓ #2a 正文里出现菜单名 ≠ 已到达(不短路 observe、不凭正文退伍)")


def test_bug2a_visible_control_triggers_real_click():
    """#2a 不误伤:目标对应一个可见导航控件时,仍发真点击(真导航)。"""
    planner = ObservationPlanner("打开订单中心", [{"action": "reach", "target": "订单中心"}])
    obs = {"body_text": "工作台", "controls": [
        {"tag": "button", "text": "订单中心", "role": "button", "disabled": False},
    ], "fields": []}
    decision = planner.decide(obs)
    assert decision.kind == "execute" and decision.action == {"action": "click", "text": "订单中心"}, \
        decision.to_dict()
    print("    ✓ #2a 存在可见导航控件 → 发真点击(click),不误伤合法导航")


def test_bug2a_arrival_verified_only_after_real_navigation():
    """#2a 到达核验:只有该导航目标此前被真导航(resolved_navigations)解析过,
    且目标现于页面出现时,才发 observe 核验到达——到达需真导航证据。"""
    planner = ObservationPlanner("打开订单中心", [{"action": "reach", "target": "订单中心"}])
    # 标记该导航目标已被有把握地点击解析过(模拟 runtime 点开网关后的状态)
    from core.ui_agent.planner import _norm_goal
    planner.state.resolved_navigations.add(_norm_goal({"action": "reach", "target": "订单中心"}))
    obs = {"body_text": "订单中心 列表加载完成", "controls": [], "fields": []}
    decision = planner.decide(obs)
    assert decision.kind == "execute" and decision.action \
        and decision.action.get("action") == "observe", \
        f"有真导航证据+目标在页 → 应 observe 核验到达:{decision.to_dict()}"
    print("    ✓ #2a 有真导航证据时才 observe 核验到达(到达 = 真导航 + 目标在页)")


def main():
    print("审计三条可信性缺陷 离线回归:\n")
    print("  [#3 field_text_equals 全文回退误通过]")
    test_bug3_field_not_found_is_inconclusive_not_false_pass()
    test_bug3_wrong_field_value_fails_not_passes()
    test_bug3_real_field_match_still_passes()
    print("\n  [#2b 是否X 伪字段断言]")
    test_bug2b_shifou_normal_extracts_no_assertion()
    test_bug2b_more_shifou_variants_extract_nothing()
    test_bug2b_real_equals_assertion_still_extracted()
    print("\n  [#2a 菜单名=已到达]")
    test_bug2a_menu_name_in_body_is_not_arrival()
    test_bug2a_visible_control_triggers_real_click()
    test_bug2a_arrival_verified_only_after_real_navigation()
    print("\n全部通过 ✅  —— 审计发现的三个误判/误通过已被回归测试锁死")


if __name__ == "__main__":
    main()
