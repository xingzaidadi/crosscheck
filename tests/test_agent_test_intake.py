from core.agent_test_intake import AgentTestRequest, build_agent_plan, validate_request


def test_natural_language_request_builds_executable_plan():
    request = AgentTestRequest(
        url="https://example.test/orders",
        instruction="点击订单管理；打开处理中；确认详情页只读",
    )
    plan = build_agent_plan(request)
    assert plan.actions
    assert any(item["action"] == "click" for item in plan.actions)
    assert plan.source_instruction == request.instruction


def test_agent_request_does_not_require_case_file_or_suite():
    request = AgentTestRequest(url="https://example.test", instruction="检查页面显示首页")
    assert validate_request(request) == []


def test_write_scope_is_required_when_write_is_authorized():
    request = AgentTestRequest(url="https://example.test", instruction="提交订单",
                               risk_policy="authorized_write", allow_write=True)
    assert validate_request(request)[0]["field"] == "write_scope"


def test_instruction_infers_query_and_first_record_actions():
    request = AgentTestRequest(
        url="https://example.test/orders",
        instruction="在客户名称输入框中输入华东并查询；打开第一条记录；确认详情显示",
    )
    plan = build_agent_plan(request)
    assert any(item.get("action") == "text" and item.get("purpose") == "query" for item in plan.actions)
    assert any(item.get("action") == "open_first_record" for item in plan.actions)


def test_high_level_goal_becomes_reachable_page_goal_without_playwright_code():
    plan = build_agent_plan(AgentTestRequest(
        url="https://example.test",
        instruction="帮我测试订单中心是否正常",
    ))
    assert {"action": "reach", "target": "订单中心"} in plan.actions


def test_immediate_natural_language_run_does_not_persist_by_default():
    request = AgentTestRequest(url="https://example.test", instruction="检查首页")
    assert request.persist_regression is False


def test_generic_health_request_becomes_observable_plan():
    plan = build_agent_plan(AgentTestRequest(
        url="https://example.test/orders",
        instruction="帮我测试订单中心是否正常",
    ))
    assert {"action": "reach", "target": "订单中心"} in plan.actions
    assert any(item["kind"] == "page_health" for item in plan.oracles)
    assert plan.clarifications == []


def test_ambiguous_request_returns_structured_clarification():
    plan = build_agent_plan(AgentTestRequest(
        url="https://example.test/orders",
        instruction="帮我看看这个系统",
    ))
    assert plan.clarifications
    assert plan.clarifications[0]["id"] == "target_or_expected_result"


def test_cross_layer_request_declares_unverified_layers():
    plan = build_agent_plan(AgentTestRequest(
        url="https://example.test/orders",
        instruction="查询订单1001，确认页面正常，并核对接口和数据库落库",
    ))
    assert plan.requested_layers == ["ui", "api", "db"]


def test_api_status_oracle_is_extracted_from_natural_language():
    plan = build_agent_plan(AgentTestRequest(
        url="https://example.test/orders",
        instruction="查询订单1001，确认接口状态码为200",
    ))
    assert plan.requested_layers == ["ui", "api"]
    assert any(item["kind"] == "api_status" and item["value"] == "200" for item in plan.oracles)


def test_db_scalar_oracle_is_extracted_from_natural_language():
    plan = build_agent_plan(AgentTestRequest(
        url="https://example.test/orders",
        instruction="提交订单后核对数据库表 orders 的 status 为 PAID",
    ))
    oracle = next(item for item in plan.oracles if item["kind"] == "db_scalar")
    assert oracle["table"] == "orders"
    assert oracle["column"] == "status"
    assert oracle["value"] == "PAID"


def test_quality_threshold_is_extracted():
    plan = build_agent_plan(AgentTestRequest(
        url="https://example.test/orders",
        instruction="打开订单列表，确认页面加载不超过2秒",
    ))
    assert plan.quality_thresholds["load"] == 2000


def test_navigation_sentence_is_not_misclassified_as_record_open():
    plan = build_agent_plan(AgentTestRequest(
        url="https://example.test/orders",
        instruction="打开订单中心，确认订单列表显示，并确认详情页只读",
    ))
    assert {"action": "click", "text": "订单中心"} in plan.actions
    assert not any(item.get("action") == "open_first_record" for item in plan.actions)


def test_explicit_first_record_sentence_keeps_record_action():
    plan = build_agent_plan(AgentTestRequest(
        url="https://example.test/orders",
        instruction="打开订单列表的第一条记录，确认详情页只读",
    ))
    assert any(item.get("action") == "open_first_record" for item in plan.actions)


def test_detail_page_expectation_requires_detail_navigation_action():
    plan = build_agent_plan(AgentTestRequest(
        url="https://example.test/orders",
        instruction="打开订单中心，确认订单列表显示，并确认详情页只读",
    ))
    assert {"action": "click", "text": "详情"} in plan.actions
    assert any(item["kind"] == "detail_page" for item in plan.oracles)


def test_query_value_precedes_query_button_and_status_is_assertable():
    plan = build_agent_plan(AgentTestRequest(
        url="https://example.test/orders",
        instruction="查询订单1001，并确认状态为待处理",
    ))
    query_input = next(index for index, item in enumerate(plan.actions) if item.get("action") == "search_value")
    query_button = next(index for index, item in enumerate(plan.actions)
                        if item.get("action") == "click" and item.get("text") == "查询")
    assert query_input < query_button
    assert any(item["kind"] == "field_text_equals" and item["value"] == "状态"
               for item in plan.oracles)
