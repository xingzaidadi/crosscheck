"""crosscheck spec-review-autogen —— 用例原意 vs 转出操作的语义复核快照(档位B,可复现)。

CP-1' 语义软门 spec_checker 的档位A 是**词法覆盖**:用例"下单"、转出操作"提交订单"
词面零重合 → 误报"覆盖不足/臆造"。档位B(LLM)判"语义是否忠实",补这层盲区。

分档(与 oracle_autogen 同构):
  - 档位A(默认):core.spec_checker.review_spec 词法覆盖,零模型、可复现。
  - 档位B(--llm,默认关):从 registry 取 spec_reviewer/default(workspace 插件注册才有),
    把用例原意+转出操作喂 LLM 判语义忠实度;没注册→自动降级档位A,不阻塞、不编数。

可复现红线(关键,照搬 oracle 档位B):档位B 的 LLM 复核**天然不可复现**。为守住
  crosscheck『可复现』铁律,生成时真调一次模型、把每条结果冻结进**复核快照**;之后
  判定只 --from-snapshot 从快照确定性读回,**绝不重调模型**。模型调用与判定物理隔离。

红线:
  - 只产复核候选(status=semantic_ok/needs_human_review),绝不改 exec_spec、绝不自动打回。
  - core 零业务:复核口径走通用分词(档位A)或用例文本派生(档位B prompt),不内置业务词典。

用法:
  # 档位A 词法复核,产复核报告(不改用例)
  python scripts/spec_review_autogen.py --suite workspace/suites/<id> --workspace workspace
  # 档位B 生成复核快照(需 workspace 注册 spec_reviewer,默认降级A)
  python scripts/spec_review_autogen.py --suite workspace/suites/<id> --workspace workspace --llm --output spec-snap.json
  # 可复现复核:从快照确定性读回,不重调模型
  python scripts/spec_review_autogen.py --suite workspace/suites/<id> --from-snapshot spec-snap.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402

from core.spec_checker import (  # noqa: E402
    STATUS_OK, STATUS_REVIEW, freeze_review, review_from_snapshot,
    review_spec, _snapshot_index,
)

_ROOT = Path(__file__).resolve().parent.parent


def _case_files(suite_dir: Path) -> list[Path]:
    return sorted((suite_dir / "cases").glob("*.yaml"))


def _exec_spec_from_case(case: dict, case_id: str) -> dict:
    """从原始 case 构造 checker 能吃的最小 exec_spec(带原文副本 + 已有转出操作)。"""
    actions = case.get("actions") or {}
    assertions = case.get("assertions") or {}
    return {
        "case_id": case_id,
        "title": str(case.get("title") or ""),
        "raw": {
            "steps": str(actions.get("source_text") or ""),
            "expected": str(assertions.get("source_text") or ""),
        },
        "ui": {"actions": actions.get("ui") or []},
        "endpoints": actions.get("api") or [],
        "assertions": {k: v for k, v in assertions.items() if k != "source_text"},
        "request": {},
    }


def _llm_review(exec_spec: dict, case_id: str) -> dict | None:
    """档位B:从 registry 取 spec_reviewer/default;没注册/异常→None(降级档位A)。

    插件契约:review(case_id=, steps=, expected=, title=, ui=, request=, endpoints=, assertions=) -> dict|None。
    core 不硬接模型;真实 LLM 客户端在 workspace/plugins/spec_reviewer.py 里注册。
    """
    try:
        from core.registry import get
        reviewer = get("spec_reviewer", "default")
    except Exception:
        reviewer = None
    if reviewer is None:
        return None
    raw = (exec_spec.get("raw") or {})
    try:
        out = reviewer(
            case_id=case_id, steps=str(raw.get("steps") or ""),
            expected=str(raw.get("expected") or ""), title=str(exec_spec.get("title") or ""),
            ui=exec_spec.get("ui") or {}, request=exec_spec.get("request") or {},
            endpoints=exec_spec.get("endpoints") or [], assertions=exec_spec.get("assertions") or {})
    except Exception:
        return None
    return out if isinstance(out, dict) else None


def run(suite: str, workspace: str | None, use_llm: bool,
        snapshot: dict | None = None) -> dict:
    """逐用例语义复核 + 冻结快照。

    snapshot 非空 → 可复现复核(只从快照读回,绝不调模型);为空 → 现复核
    (档位A 本就可复现;档位B 现复核仅用于『生成快照』一次性动作,结果冻进报告)。
    """
    suite_dir = Path(suite)
    if workspace:
        os.environ.setdefault("CROSSCHECK_WORKSPACE", workspace)
    files = _case_files(suite_dir)
    report = {"suite": str(suite_dir), "cases_total": len(files),
              "semantic_ok": 0, "needs_review": 0, "llm_hit": 0,
              "mode": ("snapshot" if snapshot else ("B(llm)" if use_llm else "A(lexical)")),
              "reviews": []}
    snap_index = _snapshot_index(snapshot) if snapshot else {}

    for path in files:
        case = yaml.safe_load(path.read_text(encoding="utf-8"))
        case_id = str(case.get("case_id") or path.stem)
        key = str((case.get("source") or {}).get("case_key") or "")
        exec_spec = _exec_spec_from_case(case, case_id)

        used_llm = False
        if snapshot is not None:
            review = review_from_snapshot(exec_spec, snap_index)
            used_llm = review.get("tier") == "llm"
        else:
            review = review_spec(exec_spec)
            if use_llm:
                verdict = _llm_review(exec_spec, case_id)
                if isinstance(verdict, dict):
                    status = str(verdict.get("status") or "")
                    if status not in {STATUS_OK, STATUS_REVIEW}:
                        status = STATUS_OK if verdict.get("faithful") else STATUS_REVIEW
                    review = dict(review)
                    review["tier"] = "llm"
                    review["status"] = status
                    review["faithful"] = bool(verdict.get("faithful", status == STATUS_OK))
                    review["reasons"] = list(review.get("reasons") or []) + list(verdict.get("reasons") or [])
                    review["semantic_gaps"] = list(verdict.get("semantic_gaps") or [])
                    used_llm = True

        if review.get("status") == STATUS_OK:
            report["semantic_ok"] += 1
        else:
            report["needs_review"] += 1
        if used_llm:
            report["llm_hit"] += 1

        frozen = freeze_review(case_id, review)
        frozen["case_key"] = key
        report["reviews"].append(frozen)

    report["ok_rate"] = round(report["semantic_ok"] / len(files), 4) if files else 0.0
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="用例原意 vs 转出操作的语义复核快照(档位B,可复现)")
    ap.add_argument("--suite", required=True)
    ap.add_argument("--workspace")
    ap.add_argument("--llm", action="store_true",
                    help="开档位B(需 workspace 注册 spec_reviewer,默认降级A)")
    ap.add_argument("--from-snapshot", dest="from_snapshot",
                    help="从复核快照可复现读回(只从快照,不重调模型)")
    ap.add_argument("--output", default="spec-review-autogen.json")
    args = ap.parse_args()

    snapshot = None
    if args.from_snapshot:
        snapshot = json.loads(Path(args.from_snapshot).read_text(encoding="utf-8"))

    report = run(args.suite, args.workspace, args.llm, snapshot=snapshot)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"套件 {report['cases_total']} 条 · 模式 {report['mode']}")
    print(f"  语义忠实(semantic_ok) {report['semantic_ok']} = {report['ok_rate']:.1%}")
    print(f"  待人审(needs_human_review) {report['needs_review']}")
    if report["llm_hit"]:
        print(f"  档位B(LLM)复核 {report['llm_hit']} 条")
    print(f"写出:{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
