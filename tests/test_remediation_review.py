import json

import pytest
import yaml

from core.remediation_review import review_draft, validate_draft
from core.precondition_readiness import assess_case_preconditions
from core.oracle_readiness import assess_case_oracles


def _plan(tmp_path):
    plan = {
        "mode": "review_only",
        "tasks": [{"draft_asset_id": "fixture:one", "status": "draft"},
                   {"draft_asset_id": "oracle:one", "status": "draft"}],
        "fixture_drafts": [{
            "fixture_id": "fixture:one", "case_keys": ["TC1"], "strategy": "api_workflow",
            "steps": [{"method": "POST", "url": "/orders"}],
            "cleanup_contract": {"required": True, "declared": True},
        }],
        "oracle_drafts": [{
            "oracle_id": "oracle:one", "case_id": "suite/TC1",
            "assertions": [{"id": "status", "proof": "api_response", "expected": "ok"}],
        }],
    }
    path = tmp_path / "remediation_plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    return path


def test_approved_fixture_is_written_to_separate_approved_assets(tmp_path):
    plan = _plan(tmp_path)
    result = review_draft(plan, tmp_path / "suite", "fixture:one", reviewer="qa",
                          decision="approve", evidence=["fixture-review.md"])
    approved = tmp_path / "suite" / "approved_assets" / "fixtures"
    assert result["decision"] == "approve"
    assert list(approved.glob("*.yaml"))
    updated = json.loads(plan.read_text(encoding="utf-8"))
    assert updated["tasks"][0]["status"] == "approved"
    assert updated["review_audit"][0]["reviewer"] == "qa"
    assert yaml.safe_load(next(approved.glob("*.yaml")).read_text(encoding="utf-8")).get("verified") is True


def test_approved_assets_close_precondition_and_oracle_gaps(tmp_path):
    plan = _plan(tmp_path)
    suite = tmp_path / "suite"
    review_draft(plan, suite, "fixture:one", reviewer="qa", decision="approve")
    review_draft(plan, suite, "oracle:one", reviewer="qa", decision="approve")
    case = {
        "case_id": "suite/TC1", "source": {"case_key": "TC1"},
        "data": {"preconditions_text": "存在订单"},
        "evidence": {"required": ["api_response"]},
    }
    assert assess_case_preconditions(case, suite_dir=suite)["status"] == "ready"
    assert assess_case_oracles(case, suite_dir=str(suite))["status"] == "ready"


def test_incomplete_oracle_cannot_be_approved(tmp_path):
    assert validate_draft("oracle", {"assertions": [{"id": "x"}]})
    plan = _plan(tmp_path)
    raw = json.loads(plan.read_text(encoding="utf-8"))
    raw["oracle_drafts"][0]["assertions"] = []
    plan.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="not approvable"):
        review_draft(plan, tmp_path / "suite", "oracle:one", reviewer="qa", decision="approve")


def test_rejection_does_not_create_executable_asset(tmp_path):
    plan = _plan(tmp_path)
    review_draft(plan, tmp_path / "suite", "oracle:one", reviewer="qa", decision="reject")
    assert not (tmp_path / "suite" / "approved_assets").exists()
