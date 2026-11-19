from __future__ import annotations

import json
from pathlib import Path

from scripts.gap_triage import triage


def test_gap_triage_preserves_no_guessing_policy(tmp_path: Path):
    (tmp_path / "gap_report.json").write_text(json.dumps({"gaps": [
        {"case_id": "suite/C1", "gap_id": "g1", "type": "FIXTURE_MISSING", "reason": "missing recipe"},
        {"case_id": "suite/C1", "gap_id": "g2", "type": "BINDING_REVIEW_REQUIRED", "reason": "review"},
    ]}), encoding="utf-8")
    (tmp_path / "readiness.json").write_text(json.dumps([{"case_id": "suite/C1", "status": "BLOCKED"}]), encoding="utf-8")
    result = triage(tmp_path)
    assert result["policy"]["no_guessing"] is True
    assert result["counts"]["FIXTURE_RECIPE_REQUIRED"] == 1
    assert result["counts"]["CANDIDATE_REVIEW_REQUIRED"] == 1
