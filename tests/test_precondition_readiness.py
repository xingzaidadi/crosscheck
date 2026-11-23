import json

from core.precondition_readiness import assess_case_preconditions, assess_preconditions


def test_verified_fixture_makes_declared_precondition_ready(tmp_path):
    suite = tmp_path / "suite"
    suite.mkdir()
    (suite / "fixtures.yaml").write_text(
        "fixtures:\n  paid_order:\n    verified: true\n    case_keys: [TC01]\n", encoding="utf-8"
    )
    result = assess_case_preconditions({
        "case_id": "suite/TC01", "source": {"case_key": "TC01"},
        "data": {"preconditions_text": "存在已支付订单"},
    }, suite_dir=suite)
    assert result["status"] == "ready"
    assert result["signals"][0]["kind"] == "fixture"


def test_declared_text_without_executable_source_is_blocked(tmp_path):
    result = assess_case_preconditions({
        "case_id": "suite/TC02", "data": {"preconditions_text": "存在可退款订单"},
    }, suite_dir=tmp_path / "suite")
    assert result["status"] == "blocked"


def test_state_recipe_is_an_executable_source(tmp_path):
    recipes = tmp_path / "knowledge_base" / "state_recipes"
    recipes.mkdir(parents=True)
    (recipes / "order.json").write_text(json.dumps({"states": {
        "PAID": {"steps": [{"method": "POST", "url": "/orders"}]}
    }}), encoding="utf-8")
    result = assess_preconditions([{
        "case_id": "suite/TC03",
        "data": {"preconditions_text": "订单已支付"},
        "execution": {"prepare_state": {"feature": "order", "state": "PAID"}},
    }], workspace=tmp_path)
    assert result["coverage"] == 1.0
    assert result["ready"] == 1
