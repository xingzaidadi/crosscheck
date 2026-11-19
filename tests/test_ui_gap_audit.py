import json

from scripts.ui_gap_audit import audit


def test_gap_audit_summarizes_readiness_and_candidates(tmp_path):
    workspace = tmp_path / "workspace"
    report = workspace / "suites" / "demo" / "reports" / "ui_first_readiness.json"
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({"cases": [
        {"case_id": "TC1", "status": "UI_EXECUTABLE"},
        {"case_id": "TC2", "status": "UI_BINDING_REQUIRED"},
    ]}), encoding="utf-8")
    candidate = workspace / "knowledge_base" / "asset_candidates" / "a.json"
    candidate.parent.mkdir(parents=True)
    candidate.write_text(json.dumps({"state": "candidate"}), encoding="utf-8")
    result = audit(workspace)
    assert result["readiness"]["executable_rate"] == 0.5
    assert result["candidate_assets"]["states"] == {"candidate": 1}
    assert result["freshness"]["fresh"] is True
    assert result["task_queue"]["summary"]["total"] == 1
    assert result["task_queue"]["tasks"][0]["type"] == "binding_replay"
