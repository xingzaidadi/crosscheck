"""Natural-language autonomous UI testing entrypoint."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.agent_test_intake import AgentTestRequest, build_agent_plan, validate_request  # noqa: E402
from core.config import site_credentials  # noqa: E402
from core.login import LoginError, ensure_session  # noqa: E402
from core.ui_agent.hardening import find_reusable_asset, harden_run  # noqa: E402
from core.ui_agent.auth import looks_like_login, wait_for_human_login  # noqa: E402
from core.ui_agent.runtime import AgentRuntime  # noqa: E402
from core.ui_agent.capabilities import (  # noqa: E402
    connector_readiness,
    generate_scenarios,
    history_summary,
    summarize_api_payload,
)
from core.ui_agent.capabilities import extract_scalar  # noqa: E402
from core.ui_agent.connectors import cross_layer_plan, db_scalar_check, event_readiness  # noqa: E402
from core.workspace import set_workspace  # noqa: E402
from scripts.ui_run import _profile_for_url  # noqa: E402


def run(args) -> dict:
    workspace = Path(args.workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    set_workspace(workspace)
    instruction = args.instruction
    if getattr(args, "answer", None):
        instruction = f"{instruction}\n用户补充：" + "；".join(args.answer)
    request = AgentTestRequest(
        url=args.url, instruction=instruction, role=args.role,
        risk_policy=args.risk_policy, allow_write=args.allow_write,
        write_scope=args.write_scope or "", persist_regression=not args.no_persist,
    )
    missing = validate_request(request)
    run_id = args.run_id or f"agent_test_{time.strftime('%Y%m%d_%H%M%S')}"
    run_dir = workspace / "reports" / "agent-tests" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if missing:
        return {"status": "NEEDS_INPUT", "missing_information": missing, "run_id": run_id}
    plan = build_agent_plan(request)
    if plan.clarifications:
        return {
            "status": "NEEDS_INPUT",
            "run_id": run_id,
            "plan": plan.to_dict(),
            "clarifications": plan.clarifications,
        }
    if plan.unresolved_expectations:
        return {"status": "NEEDS_INPUT", "run_id": run_id, "plan": plan.to_dict(),
                "missing_information": [{
                    "field": "expected_result",
                    "message": "以下预期无法从页面客观判定，请补充可观察标准",
                    "value": item,
                } for item in plan.unresolved_expectations]}
    session = args.session or ""
    profile = _profile_for_url(workspace, args.url)
    if profile and not args.no_session_refresh:
        try:
            session = ensure_session(profile, site_credentials(profile.site), session_file=session)
        except (LoginError, OSError, ValueError) as exc:
            return {"status": "AUTH_REQUIRED", "reason": str(exc), "run_id": run_id,
                    "plan": plan.to_dict()}
    elif session and not Path(session).is_file():
        return {"status": "AUTH_REQUIRED", "reason": "session file does not exist", "run_id": run_id,
                "plan": plan.to_dict()}
    reusable_asset = find_reusable_asset(workspace, plan.to_dict())
    if reusable_asset:
        plan.actions = list((reusable_asset.get("payload") or {}).get("actions") or plan.actions)
        plan.oracles = list((reusable_asset.get("payload") or {}).get("oracles") or plan.oracles)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed)
        context_args = {"storage_state": session} if session else {}
        context = browser.new_context(**context_args)
        page = context.new_page()
        api_events = []

        def capture_response(response):
            if response.request.resource_type not in {"xhr", "fetch"}:
                return
            event = {
                "method": response.request.method,
                "url": response.url,
                "status": response.status,
                "resource_type": response.request.resource_type,
            }
            try:
                event["content_type"] = response.headers.get("content-type", "")
            except Exception:
                event["content_type"] = ""
            if "json" in event["content_type"].lower():
                try:
                    event["body"] = summarize_api_payload(response.json())
                except Exception:
                    event["body"] = "[unavailable]"
            api_events.append(event)

        page.on("response", capture_response)
        page.goto(plan.url, wait_until="domcontentloaded", timeout=20000)
        if looks_like_login(page):
            if not args.interactive_login:
                context.close()
                browser.close()
                return {"status": "AUTH_REQUIRED", "reason": "login page detected", "run_id": run_id,
                        "plan": plan.to_dict()}
            if not args.headed:
                context.close()
                browser.close()
                return {"status": "AUTH_REQUIRED",
                        "reason": "login page detected; rerun with --headed for one-time human handoff",
                        "run_id": run_id, "plan": plan.to_dict()}
            if not wait_for_human_login(page):
                context.close()
                browser.close()
                return {"status": "AUTH_REQUIRED", "reason": "human login timed out", "run_id": run_id,
                        "plan": plan.to_dict()}
            discovered_session = workspace / ".auth" / "discovered-session.json"
            discovered_session.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(discovered_session))
        runtime = AgentRuntime(policy=request.risk_policy, allow_write=request.allow_write,
                               write_scope=request.write_scope, max_steps=args.max_steps)
        execution = runtime.run(page, plan, run_dir / "evidence").to_dict()
        if "api" in plan.requested_layers:
            api_path = run_dir / "evidence" / "api-events.json"
            api_path.write_text(json.dumps(api_events, ensure_ascii=False, indent=2), encoding="utf-8")
            execution.setdefault("evidence", []).append(str(api_path))
        context.close()
        browser.close()
    hardening = harden_run(workspace=workspace, plan=plan.to_dict(), result=execution) \
        if request.persist_regression else {
            "status": "NOT_SAVED",
            "message": "即时测试默认不沉淀回归资产；使用 --save-regression 可保存成功轨迹",
        }
    layer_status = {"ui": {"status": execution["status"], "evidence": execution.get("evidence", [])}}
    if "api" in plan.requested_layers:
        api_events = []
        api_file = run_dir / "evidence" / "api-events.json"
        if api_file.is_file():
            api_events = json.loads(api_file.read_text(encoding="utf-8"))
        api_oracles = [item for item in plan.oracles if item.get("kind") in {"api_status", "api_observed"}]
        api_field_oracles = [item for item in plan.oracles if item.get("kind") == "api_field"]
        status_expectation = next((item for item in api_oracles if item.get("kind") == "api_status"), None)
        if status_expectation:
            expected_status = int(status_expectation["value"])
            matching = [item for item in api_events if int(item.get("status") or 0) == expected_status]
            api_verdict = "PASSED" if matching else "FAILED"
        elif api_events:
            api_verdict = "OBSERVED"
        else:
            api_verdict = "INCONCLUSIVE"
        field_results = []
        for oracle in api_field_oracles:
            matches = [event for event in api_events if isinstance(event.get("body"), (dict, list))]
            actual_values = [extract_scalar(event["body"], oracle["path"]) for event in matches]
            passed = any(str(value) == str(oracle["value"]) for value in actual_values)
            field_results.append({"path": oracle["path"], "expected": oracle["value"],
                                  "actual": actual_values, "passed": passed})
        if field_results and not all(item["passed"] for item in field_results):
            api_verdict = "FAILED"
        elif field_results:
            api_verdict = "PASSED"
        layer_status["api"] = {
            "status": api_verdict,
            "events": len(api_events),
            "field_results": field_results,
            "message": "captured browser XHR/fetch metadata; response-body assertions require an explicit oracle",
        }
    if "db" in plan.requested_layers:
        db_oracle = next((item for item in plan.oracles if item.get("kind") == "db_scalar"), None)
        layer_status["db"] = db_scalar_check(
            workspace,
            table=db_oracle["table"], column=db_oracle["column"], expected=db_oracle["value"],
        ) if db_oracle else {
            "status": "NEEDS_CONFIG",
            "message": "database verification requires a workspace DB connector and an explicit data oracle",
        }
    if "event" in plan.requested_layers:
        layer_status["event"] = event_readiness(workspace)
    readiness = connector_readiness(workspace)
    cross_layer = cross_layer_plan(workspace, plan.requested_layers)
    for layer in ("db", "event"):
        if layer in plan.requested_layers and readiness[layer]["status"] == "AVAILABLE":
            layer_status[layer]["status"] = "READY"
            layer_status[layer]["message"] = readiness[layer]["message"]
    layer_blockers = [
        layer for layer, value in layer_status.items()
        if layer != "ui" and value.get("status") in {"FAILED", "NEEDS_CONFIG", "INCONCLUSIVE"}
    ]
    if layer_blockers and execution.get("status") == "PASSED":
        execution["status"] = "INCONCLUSIVE"
        execution["error"] = "cross-layer evidence incomplete: " + ", ".join(layer_blockers)
    visual = {"status": "NOT_REQUESTED"}
    if any(term in request.instruction.lower() for term in ("视觉", "截图", "布局", "样式", "visual", "layout")):
        from core.visual_gate import compare
        from core.visual_store import VisualBaselineStore
        after_image = run_dir / "evidence" / "after.png"
        component = plan.plan_id
        store = VisualBaselineStore(workspace / "artifacts" / "visual-baselines")
        try:
            baseline = store.get(component)
            visual = {"status": "PASSED" if after_image.is_file() and compare(
                baseline["path"], after_image, threshold=0.01).get("passed") else "FAILED",
                "component": component, "baseline": baseline}
            if after_image.is_file():
                visual["comparison"] = compare(baseline["path"], after_image, threshold=0.01)
        except FileNotFoundError:
            visual = {"status": "CANDIDATE", "component": component,
                      "message": "no approved baseline; review the captured after.png before recording it"}
    report = {"status": execution["status"], "run_id": run_id, "plan": plan.to_dict(),
              "execution": execution, "layers": layer_status, "hardening": hardening,
              "capabilities": {
                  "scenarios": generate_scenarios(request.instruction),
                  "connector_readiness": readiness,
                  "cross_layer_plan": cross_layer,
                  "visual": visual,
                  "role": request.role,
                  "history": history_summary(workspace),
              },
              "report_dir": str(run_dir)}
    report["asset_reused"] = bool(reusable_asset)
    if reusable_asset:
        report["asset_id"] = reusable_asset.get("asset_id")
    (run_dir / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="自然语言驱动的自主 UI 测试")
    parser.add_argument("--url", required=True)
    parser.add_argument("--instruction", required=True)
    parser.add_argument("--answer", action="append", default=[], help="回答澄清问题，可重复")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--role", default="default")
    parser.add_argument("--session")
    parser.add_argument("--risk-policy", choices=("read_only", "authorized_write"), default="read_only")
    parser.add_argument("--allow-write", action="store_true")
    parser.add_argument("--write-scope")
    parser.add_argument("--run-id")
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--headed", action="store_true")
    persistence = parser.add_mutually_exclusive_group()
    persistence.add_argument("--save-regression", action="store_true",
                             help="将成功轨迹保存为 provisional 回归资产")
    persistence.add_argument("--no-persist", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-session-refresh", action="store_true")
    parser.add_argument("--interactive-login", action="store_true", default=True,
                        help="遇到复杂登录时允许一次人工接管，完成后自动继续")
    args = parser.parse_args()
    args.no_persist = not args.save_regression
    report = run(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASSED" else 4 if report["status"] in {"NEEDS_INPUT", "AUTH_REQUIRED", "BLOCKED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
