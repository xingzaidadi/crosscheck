"""
三段式流水线命令行入口:对一条/多条真实用例跑 spec -> actions -> evidence。

离线可跑:--plan-only 只跑 spec 段(建模 + CP-1 契约),不起浏览器、不连库,
         用于快速验证"用例转操作的产物对不对"(白盒化第一段)。
完整执行:默认跑三段(需 Playwright + 可选 DB)。

示例:
  python run_three_stage.py --cases workspace/cases/x.xlsx --workspace workspace --plan-only
  python run_three_stage.py --cases workspace/cases/x.xlsx --workspace workspace \
      --profile my-site --only TC01 --auto-verify
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.case_source import read_cases
from core.modeler import load_routes
from core.orchestrator import run_case
from core.stage_batch import run_batch
from core.circuit_breaker import BreakerPolicy
from core.stage_adapters import SpecAgent
from core.stage_contracts import STAGES, StageVerdict
from core.stage_runner import StageAgent, StageContext
from core.stage_report import write_report
from core.three_stage_wiring import build_agents, make_spec_modeler
from core.workspace import captures_dir, config_dir, kb_dir, set_workspace


class _StopAgent:
    """plan-only 用:spec 之后的段不执行,直接给"未运行"产物使 orchestrator 停在本段。"""

    def produce(self, stage: str, context: StageContext) -> dict:
        from core.stage_contracts import STAGE_ARTIFACT
        return {STAGE_ARTIFACT[stage]: {"status": "not_run", "steps": [], "evidence": []}}


def _print_outcome(result) -> None:
    mark = "完成" if result.completed else f"停在 {result.stopped_at}"
    print(f"[{result.case_id}] {mark}")
    for outcome in result.outcomes:
        tag = {"pass": "✔", "reject": "✘"}.get(outcome.verdict, "·")
        reused = " (复用)" if outcome.reused else ""
        print(f"   {tag} {outcome.stage}{reused} attempts={outcome.attempts}")
        for reason in outcome.reasons:
            print(f"       - {reason}")


def main() -> int:
    parser = argparse.ArgumentParser(description="三段式流水线:用例转操作 -> UI 操作 -> 操作后验证")
    parser.add_argument("--cases", required=True, help="散文用例文件 xlsx/csv/json/yaml")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--run-dir", default=None, help="产物与检查点输出目录(默认 <workspace>/runs/three_stage)")
    parser.add_argument("--only", default=None, help="只跑这些 case_id,逗号分隔")
    parser.add_argument("--plan-only", action="store_true", help="只跑 spec 段(建模 + CP-1),离线可跑")
    parser.add_argument("--auto-verify", action="store_true", help="建模产物自动置 human_verified(仅在已走人审流程时用)")
    parser.add_argument("--session", default=None, help="storageState 登录态文件(执行 UI 用)")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--allow-write", action="store_true")
    parser.add_argument("--db", default="", help="evidence 段对账用的只读库名(db.yaml databases.<name>)")
    parser.add_argument("--no-report", action="store_true", help="不生成 report.html")
    parser.add_argument("--threshold", type=int, default=3, help="同类问题连续失败熔断阈值(批量执行)")
    parser.add_argument("--no-breaker", action="store_true", help="批量执行不启用熔断器")
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    set_workspace(workspace)
    run_dir = Path(args.run_dir).resolve() if args.run_dir else (workspace / "runs" / "three_stage")

    raws = read_cases(args.cases)
    if args.only:
        wanted = {value.strip() for value in args.only.split(",") if value.strip()}
        raws = [raw for raw in raws if raw.case_id in wanted]
    if not raws:
        print("没有可跑的用例(检查 --cases / --only)")
        return 2
    raw_by_case = {raw.case_id: raw for raw in raws}

    routes = load_routes(config_dir() / "case_routes.yaml")

    if args.plan_only:
        spec_agent: StageAgent = SpecAgent(
            make_spec_modeler(raw_by_case, routes=routes, kb_root=kb_dir(), caps_root=captures_dir()),
            auto_verify=args.auto_verify)
        stop: StageAgent = _StopAgent()
        agents = {"spec": spec_agent, "actions": stop, "evidence": stop}
    else:
        agents = build_agents(raw_by_case, routes=routes, kb_root=kb_dir(),
                              caps_root=captures_dir(), evidence_root=run_dir,
                              auto_verify=args.auto_verify, session=args.session,
                              headed=args.headed, allow_write=args.allow_write,
                              db_name=args.db)

    completed = 0
    stopped = 0
    breaker_tripped = ""
    case_ids = list(raw_by_case)
    if args.plan_only:
        # plan-only: actions 被桩成"停",熔断无意义,逐条跑只看 spec 过闸
        for case_id in case_ids:
            result = run_case(agents, run_dir, case_id, max_retries=args.max_retries,
                              resume=not args.no_resume)
            _print_outcome(result)
            spec_ok = any(o.stage == "spec" and o.verdict == StageVerdict.PASS.value
                          for o in result.outcomes)
            completed += 1 if spec_ok else 0
            stopped += 0 if spec_ok else 1
    else:
        policy = None if args.no_breaker else BreakerPolicy(default_threshold=args.threshold)
        batch = run_batch(agents, run_dir, case_ids, max_retries=args.max_retries,
                          resume=not args.no_resume, policy=policy)
        for result in batch.results:
            _print_outcome(result)
            completed += 1 if result.completed else 0
            stopped += 0 if result.completed else 1
        if batch.stopped:
            breaker_tripped = batch.reason
            print(f"[熔断] {batch.reason}")
            print(f"[转人工] {batch.handoff_path}")

    if not args.no_report:
        report_path = write_report(run_dir)
        print(f"[报告] {report_path}")
    scope = "spec(plan-only)" if args.plan_only else "三段"
    print(f"\n[汇总] {scope} · 过闸 {completed} · 打回/停 {stopped} · 产物目录 {run_dir}")
    return 0 if stopped == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
