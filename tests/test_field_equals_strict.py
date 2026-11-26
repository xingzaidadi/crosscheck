"""缺陷2b 回归:field_text_equals 必须严格相等,不接受子串。

审计复现:实际 "100"/期望 "10" 通过、实际 "Not approved"/期望 "approved" 通过。
根因是旧逻辑 `ok = actual == expected or expected in actual`。本测试锁死严格 ==。

用轻量 fake page 直接驱动 scripts.ui_test._evaluate_oracle 的 field_text_equals 分支,
不依赖 playwright。
"""
from scripts.ui_test import _evaluate_oracle


class _Control:
    def __init__(self, value):
        self._value = value

    @property
    def first(self):
        return self

    def count(self):
        return 1

    def input_value(self):
        return self._value


class _Scope:
    def __init__(self, value):
        self._value = value

    def count(self):
        return 1

    def locator(self, _selector):
        # scope.locator("input, textarea, select").first
        return _Control(self._value)


class _Label:
    def __init__(self, value):
        self._value = value

    def count(self):
        return 1

    def locator(self, _xpath):
        # ancestor-or-self scope
        return _Scope(self._value)

    @property
    def first(self):
        return self


class _FakePage:
    """目标字段真实值 = field_value。"""
    def __init__(self, field_value):
        self._field_value = field_value

    def get_by_text(self, _label, exact=True):
        return _Label(self._field_value)


def _eval(actual_field_value, expected):
    page = _FakePage(actual_field_value)
    oracle = {"kind": "field_text_equals", "value": "状态", "expected": expected}
    return _evaluate_oracle(page, oracle)["passed"]


def test_substring_does_not_pass_numeric():
    # 实际 100,期望 10 —— 旧子串逻辑会误判 True
    assert _eval("100", "10") is False


def test_substring_does_not_pass_negation():
    # 实际 "Not approved",期望 "approved" —— 旧子串逻辑会误判 True
    assert _eval("Not approved", "approved") is False


def test_exact_equal_still_passes():
    assert _eval("approved", "approved") is True
    assert _eval("10", "10") is True


def test_missing_field_value_is_inconclusive_not_pass():
    # 取不到目标字段值 → ok=None(INCONCLUSIVE),绝不假通过
    assert _eval("", "approved") is None
