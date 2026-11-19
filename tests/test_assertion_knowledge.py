from types import SimpleNamespace

from core.assertion_knowledge import match_assertion_knowledge
from core.suite_execution import assertion_candidates
from core.exploration_plan import classify_assertion_gap, build_exploration_task


def test_approved_query_mapping_binds_display_expectation(tmp_path):
    mapping_dir = tmp_path / "knowledge_base" / "query_mapping"
    mapping_dir.mkdir(parents=True)
    (mapping_dir / "需求管理.json").write_text(
        '{"feature":"需求管理","verify_status":"human_verified",'
        '"response_field_map":{"request_title":"requestTitle"}}',
        encoding="utf-8",
    )
    spec = SimpleNamespace(
        feature="需求管理",
        ui={"extract": {"rows_selector": "tr", "columns": {"需求名称": "td:nth-child(2)"}}},
        raw={"binding_path": "suite/ui_bindings/TC1.yaml"},
    )
    result = match_assertion_knowledge(
        {"source": {"case_key": "TC1"}},
        spec,
        tmp_path,
        {"TC1:expected:1": "列表显示需求名称"},
    )
    assert result["bindings"]["TC1:expected:1"]["ref"] == "ui.extract"
    assert result["candidates"] == []


def test_unmatched_expectation_remains_inconclusive_candidate(tmp_path):
    spec = SimpleNamespace(feature="", ui={"extract": {}}, raw={})
    result = match_assertion_knowledge(
        {}, spec, tmp_path, {"TC1:expected:1": "审批事件最终写入消息总线"}
    )
    assert result["bindings"] == {}
    assert result["candidates"][0]["status"] == "UNMATCHED"


def test_generic_list_word_does_not_bind_unrelated_business_expectation(tmp_path):
    mapping_dir = tmp_path / "knowledge_base" / "query_mapping"
    mapping_dir.mkdir(parents=True)
    (mapping_dir / "需求管理.json").write_text(
        '{"feature":"需求管理","verify_status":"human_verified",'
        '"response_field_map":{"request_title":"requestTitle"}}',
        encoding="utf-8",
    )
    spec = SimpleNamespace(
        feature="需求管理",
        ui={"extract": {"columns": {"需求名称": "td:nth-child(2)"}}},
        raw={},
    )
    result = match_assertion_knowledge(
        {}, spec, tmp_path, {"TC1:expected:1": "管理员可执行列表查询、导出、受理等全部操作"}
    )
    assert result["bindings"] == {}


def test_unmatched_assertions_are_exported_as_reviewable_candidates():
    case = {"case_id": "demo/TC1", "source": {"case_key": "TC1"}}
    spec = SimpleNamespace(raw={"assertion_knowledge": {"candidates": [
        {"assertion_id": "TC1:expected:1", "text": "越权访问被拦截"}
    ]}})
    candidates = assertion_candidates(case, spec)
    assert candidates[0]["state"] == "candidate"
    assert "proof_ref" in candidates[0]["required_review"]


def test_permission_gap_requires_multiple_role_inputs():
    result = classify_assertion_gap("越权访问他人工单详情被拦截")
    assert result["gap_type"] == "ROLE_OR_AUTH_CONTEXT"
    assert not result["safe_to_auto_explore"]
    assert "role_sessions" in result["required_inputs"]


def test_read_only_gap_becomes_browser_exploration_task():
    result = build_exploration_task(
        {"case_id": "TC1", "assertion_id": "A1", "text": "详情页显示需求名称"},
        page_url="https://example.test/detail",
        session=".auth/test.json",
    )
    assert result["status"] == "READY_TO_EXPLORE"
    assert result["strategy"] == "read_only_dom_probe"
    assert "dom_snapshot" in result["evidence_required"]
