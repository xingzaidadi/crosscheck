from __future__ import annotations

from core.gap_resolutions import apply_resolutions, validate_resolutions


def test_approved_resolution_clears_only_matching_gap():
    gap = {"case_id": "suite/C1", "gap_id": "gap:suite/C1:api:binding_review_required",
           "type": "BINDING_REVIEW_REQUIRED", "layer": "api", "reason": "review"}
    plan = {"gap_report": {"gaps": [gap]},
            "readiness": [{"case_id": "suite/C1", "status": "BLOCKED", "blocking_gaps": [gap]}],
            "binding_candidates": [{"case_id": "suite/C1", "layer": "api", "target": "",
                                    "status": "REVIEW_REQUIRED", "confidence": 0.0}],
            "oracle_plan": [], "fixture_requirements": []}
    answers = {"resolutions": [{"gap_id": gap["gap_id"], "resolution_type": "binding",
                                "status": "approved", "approved_by": "owner", "value": "/api/items"}]}
    updated, audit = apply_resolutions(plan, answers)
    assert updated["readiness"][0]["status"] == "READY"
    assert updated["binding_candidates"][0]["status"] == "REVIEWED"
    assert audit["approved"] == 1


def test_approval_requires_identity_and_value():
    errors = validate_resolutions({"resolutions": [{"gap_id": "g", "resolution_type": "binding",
                                                     "status": "approved", "approved_by": ""}]})
    assert errors


def test_pending_resolution_never_clears_gap():
    gap = {"case_id": "suite/C1", "gap_id": "gap:suite/C1:api:binding_review_required",
           "type": "BINDING_REVIEW_REQUIRED", "layer": "api", "reason": "review"}
    plan = {"gap_report": {"gaps": [gap]},
            "readiness": [{"case_id": "suite/C1", "status": "BLOCKED", "blocking_gaps": [gap]}],
            "binding_candidates": [], "oracle_plan": [], "fixture_requirements": []}
    updated, audit = apply_resolutions(plan, {"resolutions": [{"gap_id": gap["gap_id"],
        "resolution_type": "binding", "status": "pending", "approved_by": "", "value": {}}]})
    assert updated["readiness"][0]["status"] == "BLOCKED"
    assert updated["gap_report"]["total"] == 1
    assert audit["approved"] == 0


def test_unknown_gap_is_rejected():
    plan = {"gap_report": {"gaps": []}, "readiness": [], "binding_candidates": [],
            "oracle_plan": [], "fixture_requirements": []}
    try:
        apply_resolutions(plan, {"resolutions": [{"gap_id": "unknown", "resolution_type": "binding",
            "status": "approved", "approved_by": "owner", "value": "/api/items"}]})
    except ValueError as error:
        assert "unknown gap_id" in str(error)
    else:
        raise AssertionError("unknown gap id must be rejected")
