import json

from core.remediation_generator import generate_remediation_plan, write_draft_assets


def test_blocked_case_generates_review_only_fixture_and_oracle_tasks(tmp_path):
    plan = generate_remediation_plan([{
        "case_id": "suite/TC01",
        "priority": "P0",
        "data": {"preconditions_text": "存在已支付订单"},
        "assertions": {"source_text": "订单状态正确"},
        "evidence": {"required": ["api_response", "db_result"]},
    }], suite_dir=tmp_path / "suite", workspace=tmp_path)
    assert plan["mode"] == "review_only"
    assert plan["task_count"] == 2
    assert {item["category"] for item in plan["tasks"]} == {"state_blocked", "oracle_blocked"}
    assert all(item["human_confirmation_required"] for item in plan["tasks"])


def test_verified_inputs_do_not_create_duplicate_remediation(tmp_path):
    suite = tmp_path / "suite"
    suite.mkdir()
    (suite / "fixtures.yaml").write_text(
        "fixtures:\n  paid_order:\n    verified: true\n    case_keys: [TC02]\n", encoding="utf-8"
    )
    recipes = tmp_path / "knowledge_base" / "state_recipes"
    recipes.mkdir(parents=True)
    (recipes / "order.json").write_text(json.dumps({"states": {
        "PAID": {"steps": [{"method": "POST", "url": "/orders"}]}
    }}), encoding="utf-8")
    plan = generate_remediation_plan([{
        "case_id": "suite/TC02", "source": {"case_key": "TC02"},
        "data": {"preconditions_text": "存在已支付订单"},
        "execution": {"prepare_state": {"feature": "order", "state": "PAID"}},
        "assertions": {"api": [{"id": "status", "proof": "api_response"}]},
        "evidence": {"required": ["api_response"]},
    }], suite_dir=suite, workspace=tmp_path)
    assert plan["task_count"] == 0


def test_draft_assets_are_written_separately(tmp_path):
    plan = generate_remediation_plan([{
        "case_id": "suite/TC03",
        "data": {"preconditions_text": "存在数据"},
        "assertions": {"source_text": "结果正确"},
    }], suite_dir=tmp_path / "suite", workspace=tmp_path)
    paths = write_draft_assets(plan, tmp_path / "drafts")
    assert len(paths) == 2
    assert all(path.exists() for path in paths)
    assert all("review" in path.read_text(encoding="utf-8") for path in paths)
