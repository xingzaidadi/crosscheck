from __future__ import annotations

from pathlib import Path

import yaml

from scripts.ui_pilot import _is_read_only, auto_progress_allowed, discover_suite, select_pilot


class Spec:
    mode = "ui"
    ui = {"page_url": "/list"}
    raw = {"canonical_case_key": "TC1"}
    case_id = "TC1"
    title = "需求列表筛选"
    level = "P0"


def test_discover_suite_matches_original_case_filename(tmp_path: Path):
    workspace = tmp_path / "workspace"
    suite = workspace / "suites" / "demo"
    suite.mkdir(parents=True)
    (suite / "suite.yaml").write_text(yaml.safe_dump({
        "suite_id": "demo", "source": {"file": "source/cases.xlsx"}
    }), encoding="utf-8")
    assert discover_suite(workspace, cases=tmp_path / "cases.xlsx").name == "demo"


def test_ui_pilot_excludes_write_like_cases():
    safe, reason = _is_read_only(Spec())
    assert safe and reason
    risky = Spec()
    risky.title = "提交需求"
    safe, reason = _is_read_only(risky)
    assert not safe
    assert "write" in reason or "workflow" in reason


def test_select_pilot_honors_explicit_only():
    first = Spec()
    second = Spec()
    second.raw = {"canonical_case_key": "TC2"}
    second.case_id = "TC2"
    selected, excluded = select_pilot([first, second], {
        "cases": [{"source_case_key": "TC1"}, {"source_case_key": "TC2"}]
    }, only="TC2", pilot_size=1)
    assert [spec.case_id for spec in selected] == ["TC2"]
    assert excluded == []


def test_auto_progress_is_blocked_by_readiness_exclusions():
    assert auto_progress_allowed([Spec()], [{"case_id": "TC2", "reason": "binding missing"}])["allowed"] is False
    assert auto_progress_allowed([Spec()], [{"case_id": "TC2", "reason": "pilot limit"}])["allowed"] is True
