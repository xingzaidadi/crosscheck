"""
三段式流水线命令行入口:对一条/多条真实用例跑 spec -> actions -> evidence。

离线单段(对称白盒化每一段,均不起浏览器/不连库,除非该段必须):
  --plan-only     只跑 spec 段(建模 + CP-1 结构门),验"用例转操作"产物对不对
  --actions-only  跑到 actions 段即停(spec→actions),验"操作计划"产物,不跑 evidence
  --evidence-only 只跑 evidence 段(复用已落盘的 spec/actions 产物),验"操作后验证"结论
  --dump <stage>  打印某用例某段已落盘产物(spec/actions/evidence/spec_review),纯查看

语义软门(CP-1'):
  --check-spec    spec 段过闸后跑语义复核 checker(maker 转、checker 挑错,互不改产物),
                  只落 spec_review 候选 + 附"语义存疑·待人审"提示,【不改过闸、不停流水线】。
  --semantic-llm  档位B 占位开关(本轮无真实模型,自动降级到档位A词法覆盖)。

完整执行:默认跑三段(需 Playwright + 可选 DB)。

示例:
  python run_three_stage.py --cases workspace/cases/x.xlsx --workspace workspace --plan-only --check-spec
  python run_three_stage.py --cases workspace/cases/x.xlsx --workspace workspace --dump spec_review --only TC01
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
from core.stage_contracts import STAGE_ARTIFACT, STAGES, StageVerdict
from core.stage_runner import StageAgent, StageContext
from core.stage_report import write_report
from core.three_stage_wiring import build_agents, build_checker, make_spec_modeler
from core.workspace import captures_dir, config_dir, kb_dir, set_workspace


class _StopAgent:
    """单段用:在某段之后不执行,直接给"未运行"产物使 orchestrator 停在前一段。"""

    def produce(self, stage: str, context: StageContext) -> dict:
        return {STAGE_ARTIFACT[stage]: {"status": "not_run", "steps": [], "evidence": []}}


class _ReplayAgent:
    """--evidence-only 用:上游段(spec/actions)不重跑,直接回放已落盘产物。

    产物已存在于 artifacts/<stage>.json(前次跑留下);回放它让 orchestrator 过闸进下一段,
    从而只对 evidence 段做单段白盒验证(确定性,不碰浏览器)。
    """

    def __init__(self, run_dir: Path, case_id: str):
        self._dir = Path(run_dir) / case_id / "artifacts"

    def produce(self, stage: str, context: StageContext) -> dict:
        key = STAGE_ARTIFACT[stage]
        path = self._dir / f"{stage}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"--evidence-only 需先有 {stage} 段产物({path});请先不带 --evidence-only 跑一遍")
        data = json.loads(path.read_text(encoding="utf-8"))
        return {key: data.get(key, data)}


def _print_outcome(result) -> None:
    mark = "完成" if result.completed else f"停在 {result.stopped_at}"
    print(f"[{result.case_id}] {mark}")
    for outcome in result.outcomes:
        tag = {"pass": "✔", "reject": "✘"}.get(outcome.verdict, "·")
        reused = " (复用)" if outcome.reused else ""
        print(f"   {tag} {outcome.stage}{reused} attempts={outcome.attempts}")
        for reason in outcome.reasons:
            print(f"       - {reason}")


def _dump_artifact(run_dir: Path, case_ids: list[str], stage: str) -> int:
    """纯查看:打印某段已落盘产物(spec/actions/evidence/spec_review),不跑任何段。"""
    valid = set(STAGES) | {"spec_review"}
    if stage not in valid:
        print(f"--dump 的段名须是 {sorted(valid)} 之一,收到 {stage!r}")
        return 2
    shown = 0
    for case_id in case_ids:
        path = Path(run_dir) / case_id / "artifacts" / f"{stage}.json"
        if not path.exists():
            print(f"[{case_id}] 无 {stage} 产物({path});请先跑对应段")
            continue
        print(f"\n===== [{case_id}] {stage} =====")
        print(path.read_text(encoding="utf-8"))
        shown += 1
    return 0 if shown else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="三段式流水线:用例转操作 -> UI 操作 -> 操作后验证")
    parser.add_argument("--cases", required=True, help="散文用例文件 xlsx/csv/json/yaml")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--run-dir", default=None, help="产物与检查点输出目录(默认 <workspace>/runs/three_stage)")
    parser.add_argument("--only", default=None, help="只跑这些 case_id,逗号分隔")
    parser.add_argument("--plan-only", action="store_true", help="只跑 spec 段(建模 + CP-1 结构门),离线可跑")
    parser.add_argument("--actions-only", action="store_true", help="跑到 actions 段即停(spec→actions),不跑 evidence")
    parser.add_argument("--evidence-only", action="store_true", help="只跑 evidence 段(回放已落盘 spec/actions 产物)")
    parser.add_argument("--dump", default=None, metavar="STAGE",
                        help="纯查看:打印某段已落盘产物(spec/actions/evidence/spec_review),不跑段")
    parser.add_argument("--check-spec", action="store_true",
                        help="开 CP-1' 语义软门:spec 过闸后跑 checker 复核(只落 spec_review+附提示,不阻断)")
    parser.add_argument("--semantic-llm", action="store_true",
                        help="语义软门档位B 占位(本轮无真实模型,自动降级到档位A词法覆盖)")
    parser.add_argument("--check-coverage", type=float, default=0.5,
                        help="语义软门档位A覆盖阈值(默认 0.5;低于则标『语义存疑·待人审』)")
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
    case_ids = list(raw_by_case)

    # --dump:纯查看已落盘产物,不跑任何段,提前返回。
    if args.dump:
        return _dump_artifact(run_dir, case_ids, args.dump)

    single_entries = [args.plan_only, args.actions_only, args.evidence_only]
    if sum(bool(x) for x in single_entries) > 1:
        print("--plan-only / --actions-only / --evidence-only 互斥,只能开一个")
        return 2

    routes = load_routes(config_dir() / "case_routes.yaml")

    # CP-1' 语义软门:--check-spec 时装配 checker(--semantic-llm 为档位B占位,本轮降级档位A)。
    checker: StageAgent | None = None
    if args.check_spec:
        checker = build_checker(min_coverage=args.check_coverage,
                                llm=("placeholder" if args.semantic_llm else None))

    def _spec_agent() -> StageAgent:
        return SpecAgent(
            make_spec_modeler(raw_by_case, routes=routes, kb_root=kb_dir(), caps_root=captures_dir()),
            auto_verify=args.auto_verify)

    offline_single = args.plan_only or args.actions_only or args.evidence_only

    completed = 0
    stopped = 0
    breaker_tripped = ""

    if offline_single:
        # 对称离线单段:逐条跑,按本段过闸与否计数(熔断在批量执行里才有意义)。
        for case_id in case_ids:
            if args.plan_only:
                stop = _StopAgent()
                agents = {"spec": _spec_agent(), "actions": stop, "evidence": stop}
                gate_stage = "spec"
            elif args.actions_only:
                full = build_agents(raw_by_case, routes=routes, kb_root=kb_dir(),
                                    caps_root=captures_dir(), evidence_root=run_dir,
                                    auto_verify=args.auto_verify, session=args.session,
                                    headed=args.headed, allow_write=args.allow_write,
                                    db_name=args.db)
                agents = {"spec": full["spec"], "actions": full["actions"], "evidence": _StopAgent()}
                gate_stage = "actions"
            else:  # evidence_only:回放 spec/actions,只真跑 evidence
                replay = _ReplayAgent(run_dir, case_id)
                full = build_agents(raw_by_case, routes=routes, kb_root=kb_dir(),
                                    caps_root=captures_dir(), evidence_root=run_dir,
                                    auto_verify=args.auto_verify, db_name=args.db)
                agents = {"spec": replay, "actions": replay, "evidence": full["evidence"]}
                gate_stage = "evidence"

            result = run_case(agents, run_dir, case_id, max_retries=args.max_retries,
                              resume=not args.no_resume, checker=checker)
            _print_outcome(result)
            gate_ok = any(o.stage == gate_stage and o.verdict == StageVerdict.PASS.value
                          for o in result.outcomes)
            completed += 1 if gate_ok else 0
            stopped += 0 if gate_ok else 1
    else:
        agents = build_agents(raw_by_case, routes=routes, kb_root=kb_dir(),
                              caps_root=captures_dir(), evidence_root=run_dir,
                              auto_verify=args.auto_verify, session=args.session,
                              headed=args.headed, allow_write=args.allow_write,
                              db_name=args.db)
        policy = None if args.no_breaker else BreakerPolicy(default_threshold=args.threshold)
        batch = run_batch(agents, run_dir, case_ids, max_retries=args.max_retries,
                          resume=not args.no_resume, policy=policy, checker=checker)
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
    scope = ("spec(plan-only)" if args.plan_only else
             "spec→actions(actions-only)" if args.actions_only else
             "evidence(evidence-only)" if args.evidence_only else "三段")
    gate_note = " · 语义软门开" if checker is not None else ""
    print(f"\n[汇总] {scope}{gate_note} · 过闸 {completed} · 打回/停 {stopped} · 产物目录 {run_dir}")
    return 0 if stopped == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
