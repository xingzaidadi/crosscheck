from core.quality_gate import evaluate_quality_gate


def _product(score=82, level="M3", preparation=1.0, oracle=1.0, inconclusive=0.0, run=True):
    return {"maturity": {"score": score, "level": level, "dimensions": {
        "preparation": preparation, "oracle": oracle,
        "inconclusive_rate": inconclusive, "has_run_evidence": run,
    }}}


def test_quality_gate_passes_only_when_all_p0_thresholds_pass():
    result = evaluate_quality_gate(_product(), {"asset_count": 1, "assets": [{"health": "healthy"}]})
    assert result["passed"] is True
    assert result["blockers"] == []


def test_quality_gate_reports_all_blocking_dimensions():
    result = evaluate_quality_gate(
        _product(score=40, level="M1", preparation=0.2, oracle=0.0, inconclusive=0.5, run=False),
        {"asset_count": 2, "assets": [{"health": "degraded"}, {"health": "unhealthy"}]},
    )
    types = {item["type"] for item in result["blockers"]}
    assert result["passed"] is False
    assert {"maturity_score", "maturity_level", "preparation_coverage", "oracle_coverage",
            "inconclusive_rate", "run_evidence_missing", "degraded_assets", "unhealthy_assets"} <= types


def test_quality_gate_can_be_used_for_progressive_rollout():
    result = evaluate_quality_gate(
        _product(score=60, level="M2", preparation=0.8, oracle=0.8, run=False),
        {"asset_count": 0, "assets": []},
        min_score=50, min_maturity="M2", min_preparation=0.8,
        min_oracle=0.8, require_run_evidence=False,
    )
    assert result["passed"] is True


def test_capability_coverage_is_enforced():
    passing = evaluate_quality_gate(
        _product(), {"asset_count": 0, "assets": []},
        domain_report={"capability_pack_valid": True, "coverage": 1.0, "missing_action_kinds": []},
    )
    assert passing["passed"] is True
    assert passing["capability"]["coverage"] == 1.0

    failing = evaluate_quality_gate(
        _product(), {"asset_count": 0, "assets": []},
        domain_report={"capability_pack_valid": True, "coverage": 0.4,
                       "missing_action_kinds": ["transition"]},
    )
    types = {item["type"] for item in failing["blockers"]}
    assert failing["passed"] is False
    assert "capability_coverage" in types
