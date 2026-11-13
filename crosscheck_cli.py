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

    test = sub.add_parser("self-test", help="运行全部离线回归")
    test.add_argument("--acceptance", action="store_true")

    demo = sub.add_parser("demo", help="运行完全本地的 UI/API/SQLite 全链路演示")
    demo.add_argument("--workspace")

    release = sub.add_parser("release", help="构建安全源码发布包")
    release.add_argument("--out")
    release.add_argument("--allow-dirty", action="store_true")

    task = sub.add_parser("task", help="创建、执行和查询持久化测试任务")
    task.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    if args.command == "doctor":
        return _run("scripts/preflight_install.py", [])
    if args.command == "init":
        return _run("scripts/init_workspace.py", [args.workspace])
    if args.command == "onboard":
        return _run("run_onboard.py", args.arguments)
    if args.command == "plan":
        values = ["--suite", args.suite, "--workspace", args.workspace, "--plan-only"]
        if args.only:
            values.extend(["--only", args.only])
        return _run("run_suite.py", values)
    if args.command == "run":
        values = ["--suite", args.suite, "--workspace", args.workspace]
        values += _forward(args, ["only", "pilot_size", "ensure_login", "no_resume", "run_id"])
        return _run("run_suite.py", values)
    if args.command == "knowledge":
        return _run("scripts/knowledge.py", args.arguments)
    if args.command == "dashboard":
        return _run("scripts/dashboard.py", _forward(args, ["workspace", "serve", "port"]))
    if args.command == "map":
        return _run("scripts/system_map.py", _forward(args, ["workspace", "output"]))
    if args.command == "readiness":
        return _run("scripts/suite_readiness.py", _forward(args, ["suite", "workspace", "output"]))
    if args.command == "demo":
        return _run("scripts/local_demo.py", _forward(args, ["workspace"]))
    if args.command == "release":
        values = ["--out", args.out] if args.out else []
        if args.allow_dirty:
            values.append("--allow-dirty")
        return _run("scripts/build_release.py", values)
    if args.command == "task":
        return _run("scripts/task.py", args.arguments)
    result = _run("run_tests.py", [])
    if result or not args.acceptance:
        return result
    return _run("scripts/acceptance_matrix.py", [])


if __name__ == "__main__":
    raise SystemExit(main())
