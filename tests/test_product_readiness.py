from core.product_readiness import assess_case_complexity, assess_product_readiness


def test_complex_cross_layer_stateful_case_is_l3():
    result = assess_case_complexity({
        "case_id": "refund",
        "title": "订单退款",
        "layers": {"required": ["ui", "api", "db"]},
        "preconditions": ["paid_order", "settled_payment"],
        "assertions": {"db": [{"id": "refund_status"}]},
    })
    assert result["level"] == "L3"
    assert result["dimensions"]["cross_system"] is True


def test_readiness_report_explains_missing_run_evidence():
    suite = {"suite_id": "demo"}
    cases = [{
        "case_id": "query",
        "title": "查询",
        "status": "ready",
        "layers": {"required": ["ui", "api"]},
        "assertions": {"api": [{"id": "status"}]},
        "approval": {"reviewer": "qa"},
        "execution": {"mode": "ui", "cleanup": []},
        "evidence": {"required": ["ui", "api_response"]},
    }]
    report = assess_product_readiness(suite, cases)
    assert report["maturity"]["level"] == "M2"
    assert report["production_readiness"] == "NOT_READY"
    assert any(item["type"] == "external_evidence_missing" for item in report["blockers"])


def test_run_report_can_raise_stability_dimension():
    report = assess_product_readiness(
        {"suite_id": "demo"},
        [{
            "case_id": "query", "title": "查询", "status": "ready",
            "layers": {"required": ["api"]},
            "assertions": {"api": [{"id": "status"}]},
            "approval": {"reviewer": "qa"},
            "execution": {"mode": "api", "cleanup": []},
            "evidence": {"required": ["api_response"]},
        }],
        run_report={"total": 10, "passed": 10, "inconclusive": 0, "soak_runs": 5},
    )
    assert report["maturity"]["dimensions"]["run_stability"] == 1.0
