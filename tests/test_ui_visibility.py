"""UI 元素可见性与启用状态断言测试。"""
from core.ui_visibility import check_visibility


class FakePage:
    def __init__(self, states):
        self.states = states

    def evaluate(self, _script, args):
        return self.states[args.get("label") or args.get("selector")]


def test_visibility_preserves_present_and_absent_behavior():
    page = FakePage({
        "保存": {"found": True, "visible": True, "enabled": True},
        "删除": {"found": True, "visible": False, "enabled": False},
        "归档": {"found": False},
        "a.edit-link": {"found": True, "visible": True, "enabled": True},
    })

    ok, _layer = check_visibility(page, [
        {"label": "保存", "present": True},
        {"label": "删除", "present": False},
        {"label": "归档", "present": False},
        {"selector": "a.edit-link", "present": True},
    ])

    assert ok is True


def test_visibility_present_fails_for_hidden_or_missing_elements():
    page = FakePage({
        "删除": {"found": True, "visible": False, "enabled": False},
        "归档": {"found": False},
    })

    hidden_ok, _layer = check_visibility(page, [{"label": "删除", "present": True}])
    missing_ok, _layer = check_visibility(page, [{"label": "归档", "present": True}])

    assert hidden_ok is False
    assert missing_ok is False


def test_visibility_can_assert_enabled_state():
    page = FakePage({
        "发策略": {"found": True, "visible": True, "enabled": True},
        "发招采": {"found": True, "visible": True, "enabled": False},
    })

    ok, layer = check_visibility(page, [
        {"label": "发策略", "present": True, "enabled": True},
        {"label": "发招采", "present": True, "enabled": False},
    ])

    assert ok is True
    assert layer["rows"][0][2] == "可见且可操作"
    assert layer["rows"][1][2] == "可见且禁用"


def test_visibility_enabled_mismatch_fails():
    page = FakePage({"签合同": {"found": True, "visible": True, "enabled": False}})

    ok, _layer = check_visibility(page, [
        {"label": "签合同", "present": True, "enabled": True},
    ])

    assert ok is False
