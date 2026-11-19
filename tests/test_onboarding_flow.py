from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

from scripts.onboarding_flow import _persist


ROOT = Path(__file__).resolve().parent.parent


def _dataset(tmp_path: Path) -> tuple[Path, Path]:
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps([{
        "case_id": "C1", "title": "query items", "priority": "P1",
        "steps": "query", "expected": "items returned", "layers": ["api"],
    }]), encoding="utf-8")
    profile = tmp_path / "profile.yaml"
    profile.write_text(yaml.safe_dump({"suite_id": "demo", "capabilities": []}), encoding="utf-8")
    return cases, profile


def test_flow_first_pass_persists_waiting_state_and_report(tmp_path: Path):
    cases, profile = _dataset(tmp_path)
    command = [sys.executable, str(ROOT / "scripts" / "onboarding_flow.py"),
               "--cases", str(cases), "--profile", str(profile),
               "--workspace", str(tmp_path / "workspace")]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["status"] == "READY_NO_EXECUTION_SUITE"
    flow_dir = Path(payload["flow_dir"])
    assert (flow_dir / "state.json").is_file()
    assert (flow_dir / "unified_report.json").is_file()
    assert Path(payload["analysis"]["resolution_template"]).is_file()


def test_unified_report_distinguishes_completed_with_remaining_gaps(tmp_path: Path):
    onboarding = tmp_path / "onboarding"
    onboarding.mkdir()
    (onboarding / "gap_report.json").write_text(json.dumps({
        "gaps": [{"gap_id": "g1", "type": "MANUAL_ONLY", "reason": "manual"}]
    }), encoding="utf-8")
    (onboarding / "resolution_audit.json").write_text(json.dumps({"approved": 0}), encoding="utf-8")
    flow_dir = tmp_path / "flow"
    flow_dir.mkdir()
    state = {"flow_id": "flow-1", "inputs": {"suite": "suite"}, "history": []}
    result = {"output": str(onboarding), "onboarding_id": "onboarding-1", "case_count": 2,
              "ready_count": 1, "gap_count": 1,
              "execution": {"status": "COMPLETED", "run_id": "r1", "summary": {"total": 1, "pass": 1}}}
    report = _persist(flow_dir, state, result)
    assert report["status"] == "COMPLETED_WITH_GAPS"
    assert json.loads((flow_dir / "state.json").read_text(encoding="utf-8"))["history"]


def test_flow_does_not_require_manual_execute_flag_when_no_gaps(tmp_path: Path, monkeypatch):
    from scripts import onboarding_flow

    cases, profile = _dataset(tmp_path)
    calls = []

    def fake_run(inputs, resolutions, execute, ensure_login, pilot_size):
        calls.append(execute)
        output = tmp_path / "onboarding"
        output.mkdir(exist_ok=True)
        (output / "gap_report.json").write_text(json.dumps({"gaps": []}), encoding="utf-8")
        (output / "resolution_audit.json").write_text(json.dumps({"approved": 0}), encoding="utf-8")
        return {"output": str(output), "onboarding_id": "onboarding-1", "case_count": 1,
                "ready_count": 1, "gap_count": 0,
                "execution": {"status": "COMPLETED"} if execute else None}

    monkeypatch.setattr(onboarding_flow, "_run_onboarding", fake_run)
    args = type("Args", (), {"workspace": str(tmp_path / "workspace"), "cases": str(cases),
                              "requirements": None, "profile": str(profile), "suite": str(tmp_path / "suite"),
                              "resolutions": None, "execute_without_gaps": False,
                              "ensure_login": False, "pilot_size": 3})()
    report = onboarding_flow.start(args)
    assert calls == [False, True]
    assert report["status"] == "COMPLETED"


def test_resume_rejects_changed_input_fingerprint(tmp_path: Path):
    from scripts.onboarding_flow import resume

    cases, profile = _dataset(tmp_path)
    flow_dir = tmp_path / "flow"
    flow_dir.mkdir()
    state = {"flow_id": "flow-stale", "inputs": {"cases": str(cases), "profile": str(profile),
                                                   "requirements": "", "suite": "",
                                                   "workspace": str(tmp_path / "workspace")},
             "resolution_template": str(tmp_path / "resolution.yaml")}
    (flow_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
    (tmp_path / "resolution.yaml").write_text("resolutions: []\n", encoding="utf-8")
    args = type("Args", (), {"continue_flow": str(flow_dir), "resolutions": None,
                              "ensure_login": False, "pilot_size": 3})()
    try:
        resume(args)
    except ValueError as exc:
        assert "inputs changed" in str(exc)
    else:
        raise AssertionError("stale flow inputs must be rejected")
