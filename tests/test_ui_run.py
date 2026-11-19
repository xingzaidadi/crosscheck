import json
from pathlib import Path

from core.business_skill import write_context
from scripts.ui_run import _prepare_auto_binding_candidates, _profile_for_url
from scripts.ui_test import run
import argparse


def test_ui_run_context_can_be_written_without_secrets(tmp_path: Path):
    path = write_context(tmp_path / "reports" / "context.json", {
        "url": "https://example.test/list",
        "business_skill": {"skill_id": "demo"},
        "session": "workspace/.auth/demo.json",
    })
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["business_skill"]["skill_id"] == "demo"
    assert "password" not in data


def test_profile_matching_prefers_path_specific_profile(tmp_path: Path):
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "generic.yaml").write_text(
        "site: generic\nbase_url: https://example.test\n", encoding="utf-8"
    )
    (profiles / "orders.yaml").write_text(
        "site: orders\nbase_url: https://example.test\ndefaults:\n"
        "  probe_url: https://example.test/orders/list\n", encoding="utf-8"
    )
    from core.workspace import set_workspace
    set_workspace(tmp_path)
    assert _profile_for_url(tmp_path, "https://example.test/orders/list").site == "orders"


def test_ui_run_defaults_to_session_liveness_when_profile_matches(monkeypatch, tmp_path: Path):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "orders.yaml").write_text(
        "site: orders\nbase_url: https://example.test\n", encoding="utf-8"
    )
    from core.workspace import set_workspace
    set_workspace(tmp_path)
    profile = _profile_for_url(tmp_path, "https://example.test/orders/list")
    assert profile is not None
    assert profile.session_file.endswith("orders.json")


def test_ui_run_creates_reviewable_binding_and_oracle_candidates(tmp_path: Path):
    cases = tmp_path / "cases.csv"
    cases.write_text("name,steps_text,expected_text\nTC1-查询,点击查询,显示结果\n", encoding="utf-8")

    result = _prepare_auto_binding_candidates(cases, "https://example.test/list", tmp_path / "workspace")

    assert result["candidate_count"] == 2
    assert len(result["cases"]) == 1
    assets = list((tmp_path / "workspace" / "knowledge_base" / "asset_candidates").glob("*.json"))
    assert len(assets) == 2


def test_write_execution_requires_explicit_scope(tmp_path: Path):
    cases = tmp_path / "cases.csv"
    cases.write_text("name,steps_text,expected_text\nTC1-提交,点击提交,显示成功\n", encoding="utf-8")
    result = run(argparse.Namespace(
        cases=str(cases), url="https://example.test/list", workspace=str(tmp_path / "workspace"),
        session=None, run_id=None, only=None, allow_write=True, write_scope="",
        headed=False, timeout_ms=1000, wait_ms=0,
    ))
    assert result["status"] == "NEEDS_INPUT"
    assert result["missing_information"][0]["field"] == "write_scope"
