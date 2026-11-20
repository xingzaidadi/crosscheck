from core.ui_agent.connectors import cross_layer_plan, db_scalar_check, event_readiness, reconcile_ui_api


def test_cross_layer_plan_marks_optional_connectors_explicitly(tmp_path):
    result = cross_layer_plan(tmp_path, ["ui", "api", "db", "event"])
    assert result["ui"]["status"] == "AVAILABLE"
    assert result["api"]["status"] == "AVAILABLE"
    assert result["db"]["status"] == "NEEDS_CONFIG"
    assert result["event"]["status"] == "NEEDS_CONFIG"


def test_cross_layer_plan_detects_workspace_connector(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "db.yaml").write_text("readonly:\n  dsn: sqlite:///test.db\n", encoding="utf-8")
    result = cross_layer_plan(tmp_path, ["db"])
    assert result["db"]["status"] == "READY"


def test_reconcile_ui_api_is_conservative():
    assert reconcile_ui_api("订单1001 状态 待处理", {"code": "1001", "status": "待处理"})["status"] == "PASSED"
    assert reconcile_ui_api("空页面", {"code": "1001"})["status"] == "INCONCLUSIVE"


def test_db_scalar_check_reports_missing_connector(tmp_path):
    result = db_scalar_check(tmp_path, table="orders", column="status", expected="DONE")
    assert result["status"] == "NEEDS_CONFIG"


def test_event_readiness_reports_missing_connector(tmp_path):
    assert event_readiness(tmp_path, event_name="order.created")["status"] == "NEEDS_CONFIG"
