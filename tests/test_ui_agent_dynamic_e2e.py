from types import SimpleNamespace

from core.agent_test_intake import AgentTestRequest, build_agent_plan
from core.ui_agent.runtime import AgentRuntime


def test_runtime_observes_and_opens_hidden_nested_target(tmp_path):
    html = tmp_path / "nested.html"
    html.write_text("""<!doctype html><html><body>
      <button onclick="document.getElementById('submenu').hidden=false">订单管理</button>
      <section id="submenu" hidden>
        <button onclick="document.getElementById('detail').hidden=false">订单详情</button>
      </section>
      <section id="detail" hidden><h1>订单详情</h1><input value="100" readonly></section>
    </body></html>""", encoding="utf-8")
    plan = build_agent_plan(AgentTestRequest(
        url=html.as_uri(), instruction="打开订单详情；确认“订单详情”显示；确认页面只读"
    ))
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        result = AgentRuntime().run(page, plan, tmp_path / "evidence")
        browser.close()
    assert result.status == "PASSED"
    assert result.planner_decisions[0]["kind"] == "explore"
    assert any(item["kind"] == "execute" for item in result.planner_decisions)
    assert result.actions[0]["action"]["text"] == "订单管理"
