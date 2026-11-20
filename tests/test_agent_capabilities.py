from core.ui_agent.capabilities import (
    accessibility_audit,
    connector_readiness,
    generate_scenarios,
    history_summary,
    page_map_fingerprint,
    semantic_map,
    summarize_api_payload,
)


def test_semantic_map_is_stable_and_compact():
    page_map = semantic_map({
        "url": "https://example.test/orders",
        "title": "Orders",
        "headings": ["Orders"],
        "controls": [{"text": "Search", "tag": "button", "href": ""}],
        "fields": [], "rows": [], "tables": 1, "dialogs": 0,
    })
    assert page_map["controls"][0]["name"] == "Search"
    assert page_map_fingerprint(page_map) == page_map_fingerprint(page_map)


def test_scenarios_are_safe_and_risk_aware():
    scenarios = generate_scenarios("测试订单查询和审批权限")
    ids = {item["id"] for item in scenarios}
    assert {"happy_path", "empty_query", "not_found", "authorized_role", "unauthorized_role"} <= ids
    assert all(item["risk"] == "read_only" for item in scenarios if item["id"] != "mutation_review")


def test_connector_readiness_does_not_claim_missing_external_sources(tmp_path):
    readiness = connector_readiness(tmp_path)
    assert readiness["api"]["status"] == "AVAILABLE"
    assert readiness["db"]["status"] == "NEEDS_CONFIG"
    assert readiness["event"]["status"] == "NEEDS_CONFIG"


def test_history_summary_reads_agent_reports(tmp_path):
    report = tmp_path / "reports" / "agent-tests" / "run-1"
    report.mkdir(parents=True)
    (report / "summary.json").write_text(
        '{"run_id":"run-1","status":"PASSED","plan":{"source_instruction":"检查首页"}}',
        encoding="utf-8",
    )
    summary = history_summary(tmp_path)
    assert summary["counts"] == {"PASSED": 1}
    assert summary["runs"][0]["instruction"] == "检查首页"


def test_accessibility_audit_finds_unnamed_control(tmp_path):
    html = tmp_path / "a11y.html"
    html.write_text("<button></button><input><img>", encoding="utf-8")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(html.as_uri())
        result = accessibility_audit(page)
        browser.close()
    assert result["status"] == "FINDINGS"
    assert result["issue_count"] >= 3


def test_api_summary_redacts_sensitive_fields():
    result = summarize_api_payload({"status": "OK", "token": "secret", "items": [1, 2]})
    assert result["status"] == "OK"
    assert result["token"] == "[redacted]"
