"""Single user-facing CLI for Crosscheck."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def _run(script: str, arguments: list[str]) -> int:
    environment = dict(os.environ)
    environment.setdefault("PYTHONUTF8", "1")
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT), existing_pythonpath] if existing_pythonpath else [str(ROOT)]
    )
    return subprocess.call([sys.executable, str(ROOT / script), *arguments], cwd=ROOT, env=environment)


def _forward(args: argparse.Namespace, names: list[str]) -> list[str]:
    values: list[str] = []
    for name in names:
        value = getattr(args, name, None)
        option = "--" + name.replace("_", "-")
        if isinstance(value, bool):
            if value:
                values.append(option)
        elif value not in (None, ""):
            values.extend([option, str(value)])
    return values


def main() -> int:
    parser = argparse.ArgumentParser(prog="crosscheck", description="企业 Web 系统自主测试与跨层验证")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="检查 Python、依赖和 Chromium")
    init = sub.add_parser("init", help="创建业务 workspace")
    init.add_argument("workspace")

    onboard = sub.add_parser("onboard", help="扫描并接入新系统")
    onboard.add_argument("arguments", nargs=argparse.REMAINDER)

    flow = sub.add_parser("flow", help="统一分析、补缺、复核、READY 执行和报告闭环")
    flow.add_argument("arguments", nargs=argparse.REMAINDER)

    ui_pilot = sub.add_parser("ui-pilot", help="自动发现并执行低风险 UI-only Pilot")
    ui_pilot.add_argument("--workspace", default="workspace")
    ui_pilot.add_argument("--suite")
    ui_pilot.add_argument("--cases")
    ui_pilot.add_argument("--only")
    ui_pilot.add_argument("--pilot-size", type=int, default=3)
    ui_pilot.add_argument("--run-id")
    ui_pilot.add_argument("--plan-only", action="store_true")
    ui_pilot.add_argument("--no-session-refresh", action="store_true")
    ui_pilot.add_argument("--no-resume", action="store_true")

    ui_test = sub.add_parser("ui-test", help="给定用例和环境地址，自动建模并执行 UI 测试")
    ui_test.add_argument("--cases", required=True)
    ui_test.add_argument("--url", required=True)
    ui_test.add_argument("--workspace", default="workspace")
    ui_test.add_argument("--session")
    ui_test.add_argument("--run-id")
    ui_test.add_argument("--only")
    ui_test.add_argument("--allow-write", action="store_true")
    ui_test.add_argument("--write-scope")
    ui_test.add_argument("--headed", action="store_true")
    ui_test.add_argument("--visual-baselines")
    ui_test.add_argument("--visual-threshold", type=float, default=0.0)

    ui_run = sub.add_parser("ui-run", help="URL + 用例的一键 UI-first 测试并复用业务 Skill")
    ui_run.add_argument("--cases", required=True)
    ui_run.add_argument("--url", required=True)
    ui_run.add_argument("--workspace", default="workspace")
    ui_run.add_argument("--session")
    ui_run.add_argument("--skill")
    ui_run.add_argument("--run-id")
    ui_run.add_argument("--only")
    ui_run.add_argument("--allow-write", action="store_true")
    ui_run.add_argument("--write-scope")
    ui_run.add_argument("--headed", action="store_true")
    ui_run.add_argument("--ensure-login", action="store_true")
    ui_run.add_argument("--no-session-refresh", action="store_true")
    ui_run.add_argument("--visual-baselines")
    ui_run.add_argument("--visual-threshold", type=float, default=0.0)
    agent_test = sub.add_parser("agent-test", help="自然语言驱动的自主 UI 测试")
    agent_test.add_argument("--url", required=True)
    agent_test.add_argument("--instruction", required=True)
    agent_test.add_argument("--answer", action="append", default=[], help="回答 Agent 的澄清问题，可重复")
    agent_test.add_argument("--workspace", default="workspace")
    agent_test.add_argument("--role", default="default")
    agent_test.add_argument("--session")
    agent_test.add_argument("--risk-policy", choices=("read_only", "authorized_write"), default="read_only")
    agent_test.add_argument("--allow-write", action="store_true")
    agent_test.add_argument("--write-scope")
    agent_test.add_argument("--run-id")
    agent_test.add_argument("--max-steps", type=int, default=20)
    agent_test.add_argument("--headed", action="store_true")
    agent_test.add_argument("--save-regression", action="store_true", help="保存成功轨迹供后续回归")
    agent_test.add_argument("--no-persist", action="store_true", help=argparse.SUPPRESS)
    agent_test.add_argument("--no-session-refresh", action="store_true")
    agent_test.add_argument("--history", action="store_true", help="显示最近的自然语言测试历史")
    test = sub.add_parser("test", help="自然语言优先的统一测试入口")
    test.add_argument("request", nargs="*", help="URL 和自然语言目标；URL 可放在句子任意位置")
    test.add_argument("--cases", help="xlsx/csv/json/yaml 用例文件；提供后进入用例驱动模式")
    test.add_argument("--url", dest="url_option")
    test.add_argument("--answer", action="append", default=[], help="回答 Agent 的澄清问题，可重复")
    test.add_argument("--source", action="append", help="代码、技术方案、数据库 schema 或目录，可重复")
    test.add_argument("--only")
    test.add_argument("--plan-only", action="store_true")
    test.add_argument("--workspace", default="workspace")
    test.add_argument("--headed", action="store_true")
    test.add_argument("--max-steps", type=int, default=30)
    test.add_argument("--session")
    test.add_argument("--role", default="default")
    test.add_argument("--risk-policy", choices=("read_only", "authorized_write"), default="read_only")
    test.add_argument("--allow-write", action="store_true")
    test.add_argument("--write-scope")
    test.add_argument("--run-id")
    test.add_argument("--save-regression", action="store_true", help="保存成功轨迹供后续回归")
    test.add_argument("--no-persist", action="store_true", help=argparse.SUPPRESS)
    test.add_argument("--no-session-refresh", action="store_true")
    test.add_argument("--history", action="store_true", help="显示最近的自然语言测试历史")
    maturity = sub.add_parser("maturity-acceptance", help="验收自主 UI 测试四阶段成熟度")
    maturity.add_argument("--samples", required=True)
    maturity.add_argument("--output")
    benchmark = sub.add_parser("ui-agent-benchmark", help="运行真实浏览器自主 UI 成熟度基准")
    benchmark.add_argument("--output", required=True)
    benchmark.add_argument("--repetitions", type=int, default=20)
    real_acceptance = sub.add_parser("real-ui-acceptance", help="运行真实系统自然语言 UI 验收清单")
    real_acceptance.add_argument("--manifest", required=True)
    real_acceptance.add_argument("--output", required=True)
    real_acceptance.add_argument("--workspace", default="workspace")
    case_run = sub.add_parser("case-run", help="以用例为主线执行自主 UI 测试并生成覆盖报告")
    case_run.add_argument("--cases", required=True, help="xlsx/csv/json/yaml 用例文件")
    case_run.add_argument("--url", required=True)
    case_run.add_argument("--workspace", default="workspace")
    case_run.add_argument("--source", action="append", help="代码、技术方案、数据库 schema 或目录，可重复")
    case_run.add_argument("--only")
    case_run.add_argument("--role", default="default")
    case_run.add_argument("--session")
    case_run.add_argument("--run-id")
    case_run.add_argument("--max-steps", type=int, default=30)
    case_run.add_argument("--headed", action="store_true")
    case_run.add_argument("--plan-only", action="store_true")

    ui_onboard = sub.add_parser("ui-onboard", help="用系统信息生成 profile、UI 应用模型和接入任务")
    ui_onboard.add_argument("--workspace", default="workspace")
    ui_onboard.add_argument("--system", required=True)
    ui_onboard.add_argument("--url", required=True)
    ui_onboard.add_argument("--cases", required=True)
    ui_onboard.add_argument("--login-mode", choices=["manual", "credential"], default="manual")
    ui_onboard.add_argument("--role", action="append", default=[])
    ui_onboard.add_argument("--allow-write", action="store_true")
    ui_onboard.add_argument("--cleanup")

    ui_assets = sub.add_parser("ui-assets", help="审核、激活和退役 UI binding 资产")
    ui_assets.add_argument("arguments", nargs=argparse.REMAINDER)

    gap_audit = sub.add_parser("ui-gap-audit", help="汇总 UI readiness、Binding 缺口和候选资产")
    gap_audit.add_argument("--workspace", default="workspace")
    gap_audit.add_argument("--readiness")
    gap_audit.add_argument("--output")

    plan = sub.add_parser("plan", help="评分并生成 canonical 执行计划")
    plan.add_argument("--suite", required=True)
    plan.add_argument("--workspace", default="workspace")
    plan.add_argument("--only")

    run = sub.add_parser("run", help="Pilot 后自动执行全部 READY 用例")
    run.add_argument("--suite", required=True)
    run.add_argument("--workspace", default="workspace")
    run.add_argument("--only")
    run.add_argument("--pilot-size", type=int, default=3)
    run.add_argument("--ensure-login", action="store_true")
    run.add_argument("--no-resume", action="store_true")
    run.add_argument("--run-id")
    run.add_argument("--ui-first", action="store_true")

    knowledge = sub.add_parser("knowledge", help="查询和治理项目知识")
    knowledge.add_argument("arguments", nargs=argparse.REMAINDER)

    dashboard = sub.add_parser("dashboard", help="生成或启动本地管理控制台")
    dashboard.add_argument("--workspace", default="workspace")
    dashboard.add_argument("--serve", action="store_true")
    dashboard.add_argument("--port", type=int, default=8765)

    system_map = sub.add_parser("map", help="生成 UI/API/DB/状态统一系统地图")
    system_map.add_argument("--workspace", default="workspace")
    system_map.add_argument("--output")

    readiness = sub.add_parser("readiness", help="诊断 canonical 套件 READY 缺口")
    readiness.add_argument("--suite", required=True)
    readiness.add_argument("--workspace", default="workspace")
    readiness.add_argument("--output")
    product_readiness = sub.add_parser("product-readiness", help="评估业务复杂度、自动化成熟度和生产就绪度")
    product_readiness.add_argument("--suite", required=True)
    product_readiness.add_argument("--workspace", default="workspace")
    product_readiness.add_argument("--run-report")
    product_readiness.add_argument("--output")
    product_readiness.add_argument("--markdown")
    remediation = sub.add_parser("product-remediation", help="生成前置状态和业务 Oracle 的审核草稿")
    remediation.add_argument("--suite", required=True)
    remediation.add_argument("--workspace", default="workspace")
    remediation.add_argument("--output")
    remediation.add_argument("--draft-dir")
    remediation_review = sub.add_parser("product-remediation-review", help="审核并晋级整改草稿")
    remediation_review.add_argument("--plan", required=True)
    remediation_review.add_argument("--suite", required=True)
    remediation_review.add_argument("--asset-id", required=True)
    remediation_review.add_argument("--reviewer", required=True)
    remediation_review.add_argument("--decision", choices=("approve", "reject"), required=True)
    remediation_review.add_argument("--updates")
    remediation_review.add_argument("--evidence", action="append", default=[])
    asset_health = sub.add_parser("asset-health", help="聚合 Fixture/Oracle 运行健康度")
    asset_health.add_argument("--suite", required=True)
    asset_health.add_argument("--output")
    asset_health.add_argument("--degrade-after", type=int, default=2)
    asset_health.add_argument("--unhealthy-after", type=int, default=3)
    asset_health.add_argument("--update-assets", action="store_true")
    domain_cap = sub.add_parser("domain-capability", help="评估业务域能力包覆盖率")
    domain_cap.add_argument("--suite", required=True)
    domain_cap.add_argument("--workspace", default="workspace")
    domain_cap.add_argument("--registry")
    domain_cap.add_argument("--environment", default="test")
    domain_cap.add_argument("--output")
    soak_report = sub.add_parser("soak-report", help="聚合连续运行为 soak 稳定性报告")
    soak_report.add_argument("--suite", required=True)
    soak_report.add_argument("--min-runs", type=int, default=5)
    soak_report.add_argument("--output")
    soak_report.add_argument("--summary-output")
    recertify = sub.add_parser("asset-recertify", help="重新认证 degraded/unhealthy Fixture 或 Oracle")
    recertify.add_argument("--suite", required=True)
    recertify.add_argument("--asset-type", choices=("fixture", "oracle"), required=True)
    recertify.add_argument("--asset-id", required=True)
    recertify.add_argument("action", choices=("request", "submit", "approve"))
    recertify.add_argument("--requester")
    recertify.add_argument("--reason")
    recertify.add_argument("--submitter")
    recertify.add_argument("--soak-runs", type=int)
    recertify.add_argument("--passed-runs", type=int)
    recertify.add_argument("--evidence", action="append", default=[])
    recertify.add_argument("--reviewer")
    recertify.add_argument("--minimum-soak-runs", type=int, default=5)
    quality_gate = sub.add_parser("quality-gate", help="执行统一业务质量门禁")
    quality_gate.add_argument("--suite", required=True)
    quality_gate.add_argument("--workspace", default="workspace")
    quality_gate.add_argument("--run-report")
    quality_gate.add_argument("--asset-report")
    quality_gate.add_argument("--output")
    quality_gate.add_argument("--markdown")
    quality_gate.add_argument("--min-score", type=float, default=75.0)
    quality_gate.add_argument("--min-maturity", choices=("M0", "M1", "M2", "M3", "M4"), default="M3")
    quality_gate.add_argument("--min-preparation", type=float, default=1.0)
    quality_gate.add_argument("--min-oracle", type=float, default=1.0)
    quality_gate.add_argument("--max-inconclusive", type=float, default=0.10)
    quality_gate.add_argument("--max-degraded-assets", type=int, default=0)
    quality_gate.add_argument("--max-unhealthy-assets", type=int, default=0)
    quality_gate.add_argument("--min-capability-coverage", type=float, default=1.0)
    quality_gate.add_argument("--allow-missing-capability-pack", action="store_true")
    quality_gate.add_argument("--allow-no-run", action="store_true")
    gaps = sub.add_parser("close-gaps", help="Generate review-only bindings for suite gaps")
    gaps.add_argument("--suite", required=True)
    gaps.add_argument("--workspace", default="workspace")
    gaps.add_argument("--output")
    evidence_audit = sub.add_parser("evidence-audit", help="Audit evidence by business objective")
    evidence_audit.add_argument("--suite", required=True)
    evidence_audit.add_argument("--output")
    ui_readiness = sub.add_parser("ui-readiness", help="Build UI-first readiness matrix")
    ui_readiness.add_argument("--suite", required=True)
    ui_readiness.add_argument("--plan")
    ui_readiness.add_argument("--output")
    explore = sub.add_parser("explore", help="安全只读探索未匹配断言并生成资产候选")
    explore.add_argument("--suite", required=True)
    explore.add_argument("--workspace", default="workspace")
    explore.add_argument("--only")
    explore.add_argument("--limit", type=int, default=3)
    explore.add_argument("--output")

    test = sub.add_parser("self-test", help="运行全部离线回归")
    test.add_argument("--acceptance", action="store_true")

    demo = sub.add_parser("demo", help="运行完全本地的 UI/API/SQLite 全链路演示")
    demo.add_argument("--workspace")

    release = sub.add_parser("release", help="构建安全源码发布包")
    release.add_argument("--out")
    release.add_argument("--allow-dirty", action="store_true")

    task = sub.add_parser("task", help="创建、执行和查询持久化测试任务")
    task.add_argument("arguments", nargs=argparse.REMAINDER)
    gate = sub.add_parser("feature-gate", help="评估冻结的功能级 100%% 验收门禁")
    gate.add_argument("manifest")
    gate.add_argument("results")
    visual = sub.add_parser("visual-compare", help="比较视觉 baseline 与实际截图")
    visual.add_argument("reference")
    visual.add_argument("actual")
    visual.add_argument("--threshold", type=float, default=0.0)
    visual.add_argument("--mask", action="append", default=[])
    assets = sub.add_parser("assets", help="治理录制资产候选")
    assets.add_argument("arguments", nargs=argparse.REMAINDER)
    baseline = sub.add_parser("visual-baseline", help="管理视觉 baseline")
    baseline.add_argument("arguments", nargs=argparse.REMAINDER)
    arsenal = sub.add_parser("arsenal", help="检查业务能力注册表")
    arsenal.add_argument("arguments", nargs=argparse.REMAINDER)
    requirement = sub.add_parser("mock-requirement", help="运行本地 requirement G3 验收")
    requirement.add_argument("--repetitions", type=int, default=5)
    requirement.add_argument("--output")
    audit = sub.add_parser("case-audit", help="审计 Case v2 质量与 READY 缺口")
    audit.add_argument("arguments", nargs=argparse.REMAINDER)
    g4 = sub.add_parser("mock-g4", help="运行本地 requirement→strategy G4 累计验收")
    g4.add_argument("--output")
    g5 = sub.add_parser("mock-g5", help="运行本地 requirement→strategy→delivery G5 累计验收")
    g5.add_argument("--output")
    g5_accept = sub.add_parser("mock-g5-acceptance", help="运行本地 G5 soak/故障/幂等验收")
    g5_accept.add_argument("--repetitions", type=int, default=5)
    g5_accept.add_argument("--output")
    local_accept = sub.add_parser("local-delivery-acceptance", help="生成统一本地交付验收 artifact")
    local_accept.add_argument("--repetitions", type=int, default=5)
    local_accept.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.command == "doctor":
        return _run("scripts/preflight_install.py", [])
    if args.command == "init":
        return _run("scripts/init_workspace.py", [args.workspace])
    if args.command == "onboard":
        return _run("run_onboard.py", args.arguments)
    if args.command == "flow":
        return _run("scripts/onboarding_flow.py", args.arguments)
    if args.command == "ui-pilot":
        return _run("scripts/ui_pilot.py", _forward(args, ["workspace", "suite", "cases", "only",
                                                              "pilot_size", "run_id", "plan_only",
                                                              "no_session_refresh", "no_resume"]))
    if args.command == "ui-test":
        return _run("scripts/ui_test.py", _forward(args, ["cases", "url", "workspace", "session",
                                                            "run_id", "only", "allow_write", "write_scope", "headed",
                                                            "visual_baselines", "visual_threshold"]))
    if args.command == "ui-run":
        return _run("scripts/ui_run.py", _forward(args, ["cases", "url", "workspace", "session",
                                                           "skill", "run_id", "only", "allow_write", "write_scope",
                                                           "headed", "ensure_login", "no_session_refresh",
                                                           "visual_baselines", "visual_threshold"]))
    if args.command == "agent-test":
        if args.history:
            from core.ui_agent.capabilities import history_summary
            import json
            print(json.dumps(history_summary(args.workspace), ensure_ascii=False, indent=2))
            return 0
        return _run("scripts/agent_test.py", _forward(args, ["url", "instruction", "workspace", "role",
                                                                "session", "risk_policy", "allow_write", "write_scope",
                                                                "run_id", "max_steps", "headed", "save_regression", "no_persist",
                                                                "no_session_refresh", "interactive_login"])
                     + sum((["--answer", answer] for answer in args.answer or []), []))
    if args.command == "test":
        if args.history:
            from core.ui_agent.capabilities import history_summary
            import json
            print(json.dumps(history_summary(args.workspace), ensure_ascii=False, indent=2))
            return 0
        request_text = " ".join(args.request or []).strip()
        url_match = __import__("re").search(r"(?:https?://|file:)[^\s，。；;]+", request_text)
        target_url = args.url_option or (url_match.group(0) if url_match else "")
        instruction = request_text
        if url_match:
            instruction = " ".join(
                (request_text[:url_match.start()] + " " + request_text[url_match.end():]).split()
            )
        if args.cases:
            if not target_url:
                parser.error("test --cases requires --url")
            values = ["--cases", args.cases, "--url", target_url,
                      "--workspace", args.workspace, "--max-steps", str(args.max_steps),
                      "--role", args.role, "--risk-policy", args.risk_policy]
            for name in ("session", "write_scope", "run_id"):
                value = getattr(args, name, None)
                if value:
                    values.extend(["--" + name.replace("_", "-"), str(value)])
            for name in ("allow_write", "no_persist", "no_session_refresh"):
                if getattr(args, name, False):
                    values.append("--" + name.replace("_", "-"))
            if args.only:
                values.extend(["--only", args.only])
            if args.headed:
                values.append("--headed")
            if args.plan_only:
                values.append("--plan-only")
            for source in args.source or []:
                values.extend(["--source", source])
            return _run("scripts/case_run.py", values)
        if not target_url or not instruction:
            parser.error("test requires a URL and a natural-language goal, for example: crosscheck test https://test.example.com 查询订单1001")
        return _run("scripts/agent_test.py", ["--url", target_url,
                                                "--instruction", instruction,
                                               "--workspace", args.workspace,
                                               "--role", args.role,
                                               "--risk-policy", args.risk_policy,
                                                "--max-steps", str(args.max_steps)]
                     + sum((["--answer", answer] for answer in args.answer or []), [])
                    + (["--session", args.session] if args.session else [])
                    + (["--write-scope", args.write_scope] if args.write_scope else [])
                    + (["--run-id", args.run_id] if args.run_id else [])
                    + (["--allow-write"] if args.allow_write else [])
                    + (["--headed"] if args.headed else [])
                    + (["--save-regression"] if args.save_regression else [])
                    + (["--no-persist"] if args.no_persist else [])
                    + (["--no-session-refresh"] if args.no_session_refresh else []))
    if args.command == "maturity-acceptance":
        return _run("scripts/maturity_acceptance.py", _forward(args, ["samples", "output"]))
    if args.command == "ui-agent-benchmark":
        return _run("scripts/ui_agent_benchmark.py", _forward(args, ["output", "repetitions"]))
    if args.command == "real-ui-acceptance":
        return _run("scripts/real_ui_acceptance.py", _forward(args, ["manifest", "output", "workspace"]))
    if args.command == "case-run":
        values = _forward(args, ["cases", "url", "workspace", "only", "role", "session", "run_id",
                                 "max_steps", "headed", "plan_only"])
        for source in args.source or []:
            values.extend(["--source", source])
        return _run("scripts/case_run.py", values)
    if args.command == "ui-onboard":
        values = _forward(args, ["workspace", "system", "url", "cases", "login_mode",
                                 "allow_write", "cleanup"])
        for role in args.role:
            values.extend(["--role", role])
        return _run("scripts/ui_onboard.py", values)
    if args.command == "ui-assets":
        return _run("scripts/ui_assets.py", args.arguments)
    if args.command == "ui-gap-audit":
        return _run("scripts/ui_gap_audit.py", _forward(args, ["workspace", "readiness", "output"]))
    if args.command == "plan":
        values = ["--suite", args.suite, "--workspace", args.workspace, "--plan-only"]
        if args.only:
            values.extend(["--only", args.only])
        return _run("run_suite.py", values)
    if args.command == "run":
        values = ["--suite", args.suite, "--workspace", args.workspace]
        values += _forward(args, ["only", "pilot_size", "ensure_login", "no_resume", "run_id", "ui_first"])
        return _run("run_suite.py", values)
    if args.command == "knowledge":
        return _run("scripts/knowledge.py", args.arguments)
    if args.command == "dashboard":
        return _run("scripts/dashboard.py", _forward(args, ["workspace", "serve", "port"]))
    if args.command == "map":
        return _run("scripts/system_map.py", _forward(args, ["workspace", "output"]))
    if args.command == "readiness":
        return _run("scripts/suite_readiness.py", _forward(args, ["suite", "workspace", "output"]))
    if args.command == "product-readiness":
        return _run("scripts/product_readiness.py", _forward(args, ["suite", "workspace", "run_report", "output", "markdown"]))
    if args.command == "product-remediation":
        return _run("scripts/product_remediation.py", _forward(args, ["suite", "workspace", "output", "draft_dir"]))
    if args.command == "product-remediation-review":
        values = _forward(args, ["plan", "suite", "asset_id", "reviewer", "decision", "updates"])
        for evidence in args.evidence:
            values.extend(["--evidence", evidence])
        return _run("scripts/product_remediation_review.py", values)
    if args.command == "asset-health":
        return _run("scripts/asset_health.py", _forward(args, ["suite", "output", "degrade_after",
                                                               "unhealthy_after", "update_assets"]))
    if args.command == "domain-capability":
        return _run("scripts/domain_capability.py", _forward(args, ["suite", "workspace", "registry",
                                                                    "environment", "output"]))
    if args.command == "soak-report":
        return _run("scripts/soak_report.py", _forward(args, ["suite", "min_runs", "output", "summary_output"]))
    if args.command == "asset-recertify":
        values = _forward(args, ["suite", "asset_type", "asset_id"])
        values.append(args.action)
        values += _forward(args, ["requester", "reason", "submitter", "soak_runs", "passed_runs",
                                   "reviewer", "minimum_soak_runs"])
        for evidence in args.evidence:
            values.extend(["--evidence", evidence])
        return _run("scripts/asset_recertify.py", values)
    if args.command == "quality-gate":
        return _run("scripts/quality_gate.py", _forward(args, ["suite", "workspace", "run_report",
                                                               "asset_report", "output", "markdown", "min_score",
                                                               "min_maturity", "min_preparation", "min_oracle",
                                                               "max_inconclusive", "max_degraded_assets",
                                                               "max_unhealthy_assets", "min_capability_coverage",
                                                               "allow_missing_capability_pack", "allow_no_run"]))
    if args.command == "close-gaps":
        return _run("scripts/gap_closure.py", _forward(args, ["suite", "workspace", "output"]))
    if args.command == "evidence-audit":
        return _run("scripts/evidence_audit.py", _forward(args, ["suite", "output"]))
    if args.command == "ui-readiness":
        return _run("scripts/ui_first_readiness.py", _forward(args, ["suite", "plan", "output"]))
    if args.command == "explore":
        return _run("scripts/explore.py", _forward(args, ["suite", "workspace", "only", "limit", "output"]))
    if args.command == "demo":
        return _run("scripts/local_demo.py", _forward(args, ["workspace"]))
    if args.command == "release":
        values = ["--out", args.out] if args.out else []
        if args.allow_dirty:
            values.append("--allow-dirty")
        return _run("scripts/build_release.py", values)
    if args.command == "task":
        return _run("scripts/task.py", args.arguments)
    if args.command == "feature-gate":
        return _run("scripts/feature_gate.py", [args.manifest, args.results])
    if args.command == "visual-compare":
        values = [args.reference, args.actual, "--threshold", str(args.threshold)]
        for mask in args.mask:
            values.extend(["--mask", mask])
        return _run("scripts/visual_compare.py", values)
    if args.command == "assets":
        return _run("scripts/assets.py", args.arguments)
    if args.command == "visual-baseline":
        return _run("scripts/visual_baseline.py", args.arguments)
    if args.command == "arsenal":
        return _run("scripts/arsenal.py", args.arguments)
    if args.command == "mock-requirement":
        values = ["--repetitions", str(args.repetitions)]
        if args.output:
            values.extend(["--output", args.output])
        return _run("scripts/mock_requirement_acceptance.py", values)
    if args.command == "case-audit":
        return _run("scripts/case_audit.py", args.arguments)
    if args.command == "mock-g4":
        values = []
        if args.output:
            values.extend(["--output", args.output])
        return _run("scripts/mock_g4.py", values)
    if args.command == "mock-g5":
        values = []
        if args.output:
            values.extend(["--output", args.output])
        return _run("scripts/mock_g5.py", values)
    if args.command == "mock-g5-acceptance":
        values = ["--repetitions", str(args.repetitions)]
        if args.output:
            values.extend(["--output", args.output])
        return _run("scripts/mock_g5_acceptance.py", values)
    if args.command == "local-delivery-acceptance":
        return _run("scripts/local_delivery_acceptance.py", ["--repetitions", str(args.repetitions), "--output", args.output])
    result = _run("run_tests.py", [])
    if result or not args.acceptance:
        return result
    return _run("scripts/acceptance_matrix.py", [])


if __name__ == "__main__":
    raise SystemExit(main())
