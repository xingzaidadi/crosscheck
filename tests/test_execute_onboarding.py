from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.execute_onboarding import select_ready_cases


def test_selection_requires_both_readiness_gates(tmp_path: Path):
    workspace = tmp_path / "workspace"
    suite = workspace / "suites" / "demo"
    (suite / "cases").mkdir(parents=True)
    onboarding = workspace / "onboarding" / "run"
    onboarding.mkdir(parents=True)
    suite_data = {"schema_version": 1, "suite_id": "demo", "environment": "test",
                  "authorization": {"confirmed_non_production": True}}
    (suite / "suite.yaml").write_text(yaml.safe_dump(suite_data), encoding="utf-8")
    case = {"schema_version": 1, "case_id": "demo/C1-2", "title": "C1", "suite_id": "demo",
            "status": "draft", "priority": "P1", "source": {"case_key": "C1"},
            "layers": {"required": ["api"]}, "data": {"preconditions_text": ""},
            "actions": {"source_text": "call api", "api": []},
            "assertions": {"source_text": "ok", "api": []}, "approval": {}}
    (suite / "cases" / "C1.yaml").write_text(yaml.safe_dump(case), encoding="utf-8")
    (onboarding / "readiness.json").write_text(json.dumps([
        {"case_id": "demo/C1-2", "status": "READY", "blocking_gaps": []}
    ]), encoding="utf-8")
    selected, report = select_ready_cases(onboarding, suite, workspace)
    assert selected == []
    assert report["onboarding_ready"] == 1
    assert report["suite_execution_ready"] == 0
