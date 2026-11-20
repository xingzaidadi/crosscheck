"""Executable scenario benchmark for autonomous UI exploration maturity."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.agent_test_intake import AgentTestRequest, build_agent_plan
from core.maturity_acceptance import evaluate_maturity
from core.ui_agent.hardening import harden_run
from core.ui_agent.runtime import AgentRuntime


SCENARIOS = [
    {
        "id": "nested-navigation",
        "instruction": "打开订单详情；确认“订单详情”显示；确认页面只读",
        "html": """<button onclick="submenu.hidden=false">订单管理</button>
        <section id="submenu" hidden><button onclick="detail.hidden=false">订单详情</button></section>
        <section id="detail" hidden><h1>订单详情</h1><input value="100" readonly></section>""",
    },
    {
        "id": "tabs",
        "instruction": "切换“处理中”；确认“处理中订单”显示",
        "html": """<button role="tab" onclick="panel.hidden=false">处理中</button>
        <section id="panel" hidden><h1>处理中订单</h1></section>""",
    },
    {
        "id": "first-record",
        "instruction": "打开第一条记录；确认“订单详情”显示；确认页面只读",
        "html": """<table><tbody><tr><td><button onclick="detail.hidden=false">查看详情</button></td></tr></tbody></table>
        <section id="detail" hidden><h1>订单详情</h1><input value="100" readonly></section>""",
    },
    {
        "id": "direct-detail",
        "instruction": "点击详情；确认“客户信息”显示",
        "html": """<button onclick="detail.hidden=false">详情</button>
        <section id="detail" hidden><h1>客户信息</h1></section>""",
    },
    {
        "id": "readonly-page",
        "instruction": "确认“订单编号”显示；确认页面只读",
        "html": """<h1>订单编号</h1><input value="SO-001" readonly>""",
    },
]


def run_benchmark(output: str | Path, *, repetitions: int = 20) -> dict[str, Any]:
    output_path = Path(output).resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    samples: list[dict[str, Any]] = []
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for index in range(repetitions):
            scenario = SCENARIOS[index % len(SCENARIOS)]
            scenario_dir = output_path / f"{index + 1:03d}-{scenario['id']}"
            scenario_dir.mkdir(parents=True, exist_ok=True)
            html = scenario_dir / "index.html"
            html.write_text(f"<!doctype html><html><body>{scenario['html']}</body></html>", encoding="utf-8")
            plan = build_agent_plan(AgentTestRequest(url=html.as_uri(), instruction=scenario["instruction"]))
            page = browser.new_page()
            execution = AgentRuntime().run(page, plan, scenario_dir / "evidence").to_dict()
            page.close()
            hardening = harden_run(workspace=output_path / "workspace", plan=plan.to_dict(), result=execution)
            samples.append({"scenario": scenario["id"], "status": execution["status"],
                            "plan": plan.to_dict(), "execution": execution, "hardening": hardening})
        browser.close()
    maturity = evaluate_maturity(samples)
    report = {"benchmark": "autonomous-ui-real-browser", "samples": samples, "maturity": maturity}
    (output_path / "benchmark.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
