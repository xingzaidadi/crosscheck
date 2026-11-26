"""缺陷4 回归:断言必须表达业务预期,而非只"页面没坏"。

审计问题:
  · filter_controls 旧逻辑"全页有任意 input/select/button 就通过"——页面坏了但残留
    一个按钮也 PASS。改为锚定查询区(有查询/搜索触发 + 区域内有输入控件);连查询
    触发都没有 → INCONCLUSIVE,不假通过。
  · 空条件/重置只断言 page_health+filter_controls,缺字段级业务后置断言。为 empty_query
    从动作派生 field_value_equals expected="",断言字段**确被清空**;取不到值 → INCONCLUSIVE。
  · field_value_equals 旧逻辑取不到字段时 actual=""、expected="" 会假通过;改为定位不到
    字段 → ok=None。

filter_controls / field_value_equals 用轻量 fake page 直接驱动 _evaluate_oracle;
scenario_field_oracles 为纯函数,均不依赖 playwright。
"""
import re

from scripts.ui_test import _evaluate_oracle
from core.ui_agent.capabilities import scenario_field_oracles


# ── filter_controls 的 fake page ───────────────────────────────────────
class _Loc:
    def __init__(self, count=0, inputs=0):
        self._count = count
        self._inputs = inputs

    def count(self):
        return self._count

    @property
    def first(self):
        return self

    def locator(self, selector):
        # trigger.locator(ancestor form/search) → region;region.locator(input...) → inputs
        if "input" in selector:
            return _Loc(count=self._inputs, inputs=self._inputs)
        return _Loc(count=1 if self._count else 0, inputs=self._inputs)

    def get_by_text(self, *_a, **_k):
        return _Loc(count=0)


class _FilterPage:
    """has_trigger: 是否存在查询触发;inputs: 查询区内可输入控件数。"""
    def __init__(self, has_trigger, inputs):
        self._has_trigger = has_trigger
        self._inputs = inputs

    def get_by_role(self, role, name=None):
        if role == "button" and self._has_trigger:
            return _Loc(count=1, inputs=self._inputs)
        return _Loc(count=0)

    def get_by_text(self, pattern, exact=True):
        # 退路文本触发:这里统一不命中(只走 role 分支),简化
        return _Loc(count=0)

    def locator(self, _selector):
        return _Loc(count=self._inputs, inputs=self._inputs)


def _filter(has_trigger, inputs):
    page = _FilterPage(has_trigger, inputs)
    return _evaluate_oracle(page, {"kind": "filter_controls", "value": "查询", "fields": []})["passed"]


def test_filter_controls_inconclusive_without_query_trigger():
    # 页面没有查询/搜索触发(哪怕别处有按钮)→ 无法判定查询区 → INCONCLUSIVE,不假通过
    assert _filter(has_trigger=False, inputs=5) is None


def test_filter_controls_fails_when_region_has_no_input():
    # 有查询触发但查询区内没有任何输入控件 → 查询能力实际不可用 → 不通过
    assert _filter(has_trigger=True, inputs=0) is False


def test_filter_controls_passes_with_real_query_region():
    # 有查询触发 + 区域内有输入控件 → 查询区可用 → PASS
    assert _filter(has_trigger=True, inputs=2) is True


# ── field_value_equals 的 fake page ───────────────────────────────────
class _FieldControl:
    def __init__(self, value, exists):
        self._value = value
        self._exists = exists

    @property
    def first(self):
        return self

    def count(self):
        return 1 if self._exists else 0

    def input_value(self):
        return self._value

    def inner_text(self):
        return self._value

    def locator(self, selector):
        if "input" in selector:
            return self
        if "ancestor-or-self" in selector:
            return self  # scope
        if "following" in selector:
            return _FieldControl("", False)  # 无相邻兄弟
        return self


class _FieldPage:
    """field_exists: 页面上是否真有这个字段控件。"""
    def __init__(self, value, field_exists):
        self._value = value
        self._field_exists = field_exists

    def get_by_text(self, _label, exact=True):
        return _FieldControl(self._value, self._field_exists)


def _field_equals(value, expected, field_exists):
    page = _FieldPage(value, field_exists)
    return _evaluate_oracle(
        page, {"kind": "field_value_equals", "value": "订单号", "expected": expected}
    )["passed"]


def test_field_value_equals_empty_passes_when_field_truly_empty():
    # 字段存在且值确为空,期望空 → PASS(空条件场景真·被清空)
    assert _field_equals("", "", field_exists=True) is True


def test_field_value_equals_inconclusive_when_field_missing():
    # 定位不到字段:actual="" 恰好 == expected="" 旧逻辑会假通过;新逻辑应 INCONCLUSIVE
    assert _field_equals("", "", field_exists=False) is None


def test_field_value_equals_fails_on_mismatch():
    assert _field_equals("1001", "", field_exists=True) is False


# ── scenario_field_oracles 纯函数 ─────────────────────────────────────
def test_empty_query_derives_field_emptiness_oracle():
    actions = [
        {"action": "text", "label": "订单号", "value": "", "purpose": "query",
         "scenario_mutation": "empty_query:cleared"},
        {"action": "click", "text": "查询"},
    ]
    oracles = scenario_field_oracles("empty_query", actions)
    assert any(o["kind"] == "field_value_equals" and o["value"] == "订单号"
               and o["expected"] == "" for o in oracles), oracles


def test_unlabeled_query_input_yields_no_field_oracle():
    # search_value 没有 label(通用搜索框),无法命名字段 → 不派生(零业务,不猜字段名)
    actions = [{"action": "search_value", "value": "", "purpose": "query"}]
    assert scenario_field_oracles("empty_query", actions) == []


def test_not_found_and_reset_derive_no_field_oracle():
    actions = [{"action": "text", "label": "订单号", "value": "x", "purpose": "query"}]
    assert scenario_field_oracles("not_found", actions) == []
    assert scenario_field_oracles("reset_filter", actions) == []
