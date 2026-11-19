from pathlib import Path

from core.business_skill import discover_skills, match_skill


def test_business_skill_is_discovered_and_matched_by_url(tmp_path: Path):
    pack = tmp_path / "business_skills" / "demo"
    pack.mkdir(parents=True)
    (pack / "manifest.yaml").write_text(
        "skill_id: demo\nversion: 1.2.0\nmatch:\n  hosts: [example.test]\n"
        "  paths: [/orders/*]\nprovides: [orders]\n",
        encoding="utf-8",
    )

    skills = discover_skills(tmp_path)

    assert [item.skill_id for item in skills] == ["demo"]
    matched = match_skill(tmp_path, "https://example.test/orders/list")
    assert matched and matched.version == "1.2.0"
    assert matched.provides == ["orders"]
    assert match_skill(tmp_path, "https://example.test/vendors/list") is None


def test_business_skill_rejects_path_escape(tmp_path: Path):
    pack = tmp_path / "business_skills" / "demo"
    pack.mkdir(parents=True)
    (pack / "manifest.yaml").write_text("skill_id: demo\n", encoding="utf-8")
    skill = discover_skills(tmp_path)[0]
    try:
        skill.path("../../secret")
    except ValueError as exc:
        assert "escapes" in str(exc)
    else:
        raise AssertionError("path escape should fail")


def test_business_skill_loads_runtime_assets_and_detects_drift(tmp_path: Path):
    pack = tmp_path / "business_skills" / "demo"
    (pack / "pages").mkdir(parents=True)
    (pack / "actions").mkdir()
    (pack / "assertions").mkdir()
    (pack / "manifest.yaml").write_text(
        "skill_id: demo\nversion: 1.0.0\nmatch:\n  hosts: [example.test]\n"
        "assets:\n  page_models: [pages/list.yaml]\n  actions: [actions/list.yaml]\n"
        "  assertions: [assertions/list.yaml]\n", encoding="utf-8"
    )
    (pack / "pages" / "list.yaml").write_text(
        "entry:\n  url: https://example.test/list\nselectors:\n  demand_code: td.code\n",
        encoding="utf-8",
    )
    (pack / "actions" / "list.yaml").write_text(
        "actions:\n  open_first:\n    action: click_table_cell\n", encoding="utf-8"
    )
    (pack / "assertions" / "list.yaml").write_text(
        "assertions:\n  page_size:\n    type: page_size\n    expected: 10\n", encoding="utf-8"
    )
    skill = discover_skills(tmp_path)[0]
    assert skill.page_model("https://example.test/list")["selectors"]["demand_code"] == "td.code"
    assert skill.actions()["open_first"]["action"] == "click_table_cell"
    assert skill.assertions()["page_size"]["expected"] == 10
    skill.record_health(status="HEALTHY", evidence=["report.html"])
    assert skill.health()["status"] == "HEALTHY"
    (pack / "actions" / "list.yaml").write_text(
        "actions:\n  open_first:\n    action: open_first_record\n", encoding="utf-8"
    )
    assert skill.health()["status"] == "STALE"
