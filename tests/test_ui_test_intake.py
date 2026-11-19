from types import SimpleNamespace

from core.ui_test_intake import build_ui_intent, validate_intake


def raw(**values):
    defaults = {"name": "TC1-查询详情", "case_id": "TC1", "preconditions": "",
                "steps_text": "点击“详情”", "expected_text": "显示“订单编号”", "module": "查询"}
    defaults.update(values)
    return SimpleNamespace(**defaults)


def test_builds_actions_and_visibility_oracle_without_user_binding():
    intent = build_ui_intent(raw(), "https://test.example/list")
    assert intent.actions == [{"action": "click", "text": "详情"}]
    assert intent.oracles[0].kind == "visibility"
    assert intent.oracles[0].value == "订单编号"
    assert not intent.unresolved_expectations


def test_unknown_business_expectation_stays_inconclusive():
    intent = build_ui_intent(raw(expected_text="状态映射符合业务规则"), "https://test.example")
    assert intent.oracles == []
    assert intent.unresolved_expectations == ["状态映射符合业务规则"]


def test_write_case_requires_explicit_permission():
    intent = build_ui_intent(raw(steps_text="填写后点击提交"), "https://test.example")
    assert intent.write_risk


def test_expected_write_words_do_not_block_read_only_query_case():
    intent = build_ui_intent(raw(steps_text="进入列表查看详情", expected_text="不展示已删除单据"),
                             "https://test.example")
    assert not intent.write_risk


def test_api_path_in_prose_is_not_treated_as_browser_route():
    intent = build_ui_intent(raw(steps_text="页面查询触发 /demand/api/demand/item/page"),
                             "https://test.example/purchase/demand/management")
    assert intent.page_url == "https://test.example/purchase/demand/management"


def test_compound_tab_action_is_split_into_real_control_candidates():
    intent = build_ui_intent(
        raw(steps_text="切换待处理/执行中/全部页签", expected_text=""),
        "https://test.example/list",
    )
    assert intent.actions == [
        {"action": "switch_tabs", "labels": ["待处理", "执行中", "全部"]},
        {"action": "click", "text": "全部"},
        {"action": "click", "text": "待处理"},
        {"action": "click", "text": "执行中"},
    ]


def test_intent_keeps_original_case_text_for_formal_report():
    intent = build_ui_intent(raw(preconditions="存在订单", module="订单查询"),
                             "https://test.example/list")
    assert intent.source_steps == "点击“详情”"
    assert intent.source_expected == "显示“订单编号”"
    assert intent.source_preconditions == "存在订单"
    assert intent.source_module == "订单查询"


def test_intake_extracts_common_form_actions_and_business_counts():
    intent = build_ui_intent(
        raw(steps_text="填写‘订单号’为‘REQ001’，选择‘状态’为‘待处理’，日期字段‘申请日期’为‘2026-11-18’",
            expected_text="共 2 条，包含‘REQ001’"),
        "https://test.example/list",
    )
    assert {item["action"] for item in intent.actions} >= {"text", "select", "date"}
    assert [item.kind for item in intent.oracles] == ["count", "text_contains"]


def test_structured_detail_action_and_common_business_oracles():
    intent = build_ui_intent(
        raw(steps_text="从列表点击需求单号进入详情",
            expected_text="详情只读无编辑操作\n分页重置到第 1 页\n清空已勾选行\n前端分页默认 10 条"),
        "https://test.example/list",
    )
    assert intent.actions[0] == {"action": "open_first_record", "column": "需求单号"}
    assert [item.kind for item in intent.oracles] == [
        "readonly", "pagination_page", "selected_row_count", "page_size",
    ]
    assert intent.oracles[0].fields == []


def test_detail_action_uses_generic_column_label():
    intent = build_ui_intent(
        raw(steps_text="从列表点击订单编号进入详情", expected_text="显示‘订单编号’"),
        "https://test.example/list",
    )
    assert intent.actions[0] == {"action": "open_first_record", "column": "订单编号"}


def test_intake_extracts_field_value_equality_oracle():
    intent = build_ui_intent(
        raw(expected_text="“订单状态”等于“待处理”"),
        "https://test.example/list",
    )
    assert intent.oracles[0].kind == "field_value_equals"
    assert intent.oracles[0].value == "订单状态"
    assert intent.oracles[0].expected == "待处理"


def test_intake_reports_only_user_facing_missing_information():
    missing = validate_intake(cases="cases.xlsx", base_url="")
    assert missing == [{"field": "url", "message": "请提供有效的测试环境地址（http/https）"}]
