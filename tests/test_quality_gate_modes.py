"""quality-gate off/observe/enforce modes and verification stamp."""
from core.quality_gate import evaluate_quality_gate


def _failing_reports():
    product = {"maturity": {"score": 10, "level": "M0", "dimensions": {
        "preparation": 0.0, "oracle": 0.0, "inconclusive_rate": 0.5, "has_run_evidence": False}}}
    assets = {"assets": [], "asset_count": 0}
    return product, assets


def test_enforce_is_default_and_blocks():
    product, assets = _failing_reports()
    gate = evaluate_quality_gate(product, assets)
    assert gate["passed"] is False
    assert gate["mode"] == "enforce"
    assert gate["enforced_block"] is True
    assert gate["blockers"]


def test_observe_records_would_block_but_does_not_fail():
    product, assets = _failing_reports()
    gate = evaluate_quality_gate(product, assets, mode="observe")
    assert gate["passed"] is True            # observe never blocks
    assert gate["enforced_block"] is False
    assert len(gate["would_block"]) == len(gate["blockers"])
    assert gate["would_block"]               # but it still records what would have blocked


def test_off_skips_judgment():
    product, assets = _failing_reports()
    gate = evaluate_quality_gate(product, assets, mode="off")
    assert gate["passed"] is True
    assert gate["would_block"] == []
    assert gate["skipped"] is True


def test_verification_stamp_present_and_hashable():
    product, assets = _failing_reports()
    gate = evaluate_quality_gate(product, assets, mode="observe", verified_via=["quality-gate"])
    stamp = gate["verification_stamp"]
    assert stamp["verified_via"] == ["quality-gate"]
    assert stamp["content_hash"].startswith("sha256:")


def test_verification_stamp_defaults_to_none_when_unverified():
    product, assets = _failing_reports()
    gate = evaluate_quality_gate(product, assets, mode="off")
    assert gate["verification_stamp"]["verified_via"] == ["none"]
