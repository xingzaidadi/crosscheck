import yaml
import pytest

from core.asset_recertification import (
    approve_recertification, request_recertification, submit_recertification_evidence,
)
from core.approved_assets import load_approved_assets


def _asset(tmp_path):
    path = tmp_path / "suite" / "approved_assets" / "fixtures" / "fixture_one.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump({
        "fixture_id": "fixture:one", "status": "approved", "approved_by": "qa",
        "content_hash": "old", "case_keys": ["TC1"], "steps": [{"method": "POST", "url": "/prepare"}],
        "health": {"status": "unhealthy", "consecutive_failures": 3},
    }), encoding="utf-8")
    return tmp_path / "suite"


def test_recertification_requires_request_evidence_and_approval(tmp_path):
    suite = _asset(tmp_path)
    request_recertification(suite, "fixture", "fixture:one", requester="dev", reason="fixed endpoint")
    submit_recertification_evidence(suite, "fixture", "fixture:one", submitter="qa",
                                    soak_runs=5, passed_runs=5, evidence=["soak.json"])
    result = approve_recertification(suite, "fixture", "fixture:one", reviewer="lead")
    assert result["status"] == "healthy"
    asset = yaml.safe_load((suite / "approved_assets" / "fixtures" / "fixture_one.yaml").read_text(encoding="utf-8"))
    assert asset["health"]["status"] == "healthy"
    assert asset["recertification"]["status"] == "approved"
    assert asset["content_hash"] != "old"
    assert load_approved_assets(suite, "fixtures")[0]["fixture_id"] == "fixture:one"


def test_failed_soak_cannot_be_approved(tmp_path):
    suite = _asset(tmp_path)
    request_recertification(suite, "fixture", "fixture:one", requester="dev", reason="retry")
    submit_recertification_evidence(suite, "fixture", "fixture:one", submitter="qa",
                                    soak_runs=5, passed_runs=4, evidence=["soak.json"])
    with pytest.raises(ValueError, match="evidence has not passed"):
        approve_recertification(suite, "fixture", "fixture:one", reviewer="lead")


def test_recertification_requires_minimum_soak_runs(tmp_path):
    suite = _asset(tmp_path)
    request_recertification(suite, "fixture", "fixture:one", requester="dev", reason="fixed")
    submit_recertification_evidence(suite, "fixture", "fixture:one", submitter="qa",
                                    soak_runs=2, passed_runs=2, evidence=["soak.json"])
    with pytest.raises(ValueError, match="at least 5"):
        approve_recertification(suite, "fixture", "fixture:one", reviewer="lead")


def test_pending_recertification_asset_is_not_executable(tmp_path):
    suite = _asset(tmp_path)
    request_recertification(suite, "fixture", "fixture:one", requester="dev", reason="fixed")
    assert load_approved_assets(suite, "fixtures") == []
