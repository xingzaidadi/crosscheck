from core.oracle_readiness import assess_case_oracles, assess_oracles


def test_structured_oracle_is_bound_to_required_evidence():
    result = assess_case_oracles({
        "case_id": "refund",
        "assertions": {
            "api": [{"id": "refund_status", "proof": "api_response"}],
            "db": [{"id": "order_status", "proof": "db_assertion"}],
        },
        "evidence": {"required": ["api_response", "db_result"]},
    })
    assert result["status"] == "ready"
    assert result["proof_layers"] == ["api", "db"]


def test_source_text_only_oracle_is_blocked():
    result = assess_case_oracles({
        "case_id": "query",
        "assertions": {"source_text": "页面和接口应该一致"},
        "evidence": {"required": ["screenshot", "api_response"]},
    })
    assert result["status"] == "blocked"
    assert result["oracle_count"] == 0


def test_missing_proof_layer_is_partial_not_pass():
    result = assess_oracles([{
        "case_id": "query",
        "assertions": {"api": [{"id": "status", "proof": "api_response"}]},
        "evidence": {"required": ["api_response", "db_result"]},
    }])
    assert result["partial"] == 1
    assert result["coverage"] == 0.0
