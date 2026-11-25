"""crosscheck xlayer-review-autogen —— 跨层一致性字面误报的语义复核快照(档位B,可复现)。

crosscheck 的跨层判定(reconciler 接口↔库对账、oracle 断言)是**字面/严格值比对**:
接口枚举码 COMPLETED 与库中文 已完成,字面零重合 → 误报 false mismatch。
档位B(LLM)判"接口值与库值是否语义等价",补这层盲区。

**软门旁路铁律**:本工具只对**字面已判不一致**的差异产复核候选,**绝不改主判定**
(ReconcileResult.consistent / oracle.passed 原样)。真不一致仍 FAIL 暴露,语义层只负责
把疑似字面误报标成"疑似语义等价·待人审",降低人工复核噪声。

分档(与 spec_review_autogen / oracle_autogen 同构):
  - 档位A(默认):core.xlayer_review 确定性 base,默认待人审、零模型、可复现。
  - 档位B(--llm,默认关):从 registry 取 xlayer_reviewer/default(workspace 插件注册才有),
    把接口值+库值喂 LLM 判语义等价;没注册→自动降级确定性 base,不阻塞、不编数。

可复现红线(照搬 spec/oracle 档位B):档位B 的 LLM 复核**天然不可复现**。为守住
  crosscheck『可复现』铁律,生成时真调一次模型、把每条结果冻结进**复核快照**;之后
  判定只 --from-snapshot 从快照确定性读回,**绝不重调模型**。模型调用与判定物理隔离。

输入产物形态(JSON,逐条字面不一致项),二选一:
  - reconcile 形态:{"field_samples":[{"pk","field","api","db","ok"}...], ...}(ok==False 才复核)
  - oracle 形态:{"results":[{"id","subject","expected","actual","passed"}...], ...}(passed==False 才复核)

用法:
  # 档位B 生成复核快照(需 workspace 注册 xlayer_reviewer,默认降级 base)
  python scripts/xlayer_review_autogen.py --input reconcile.json --llm --output workspace/xlayer-review.snapshot.json
  # 可复现复核:从快照确定性读回,不重调模型
  python scripts/xlayer_review_autogen.py --input reconcile.json --from-snapshot workspace/xlayer-review.snapshot.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.xlayer_review import (  # noqa: E402
    STATUS_OK, review_oracle_result, review_reconcile_result,
)


def _load_llm(use_llm: bool):
    """档位B:从 registry 取 xlayer_reviewer/default;没注册/异常→None(降级确定性 base)。

    core 不硬接模型;真实 LLM 客户端在 workspace/plugins/xlayer_reviewer.py 里注册。
    """
    if not use_llm:
        return None
    try:
        from core.registry import get
        return get("xlayer_reviewer", "default")
    except Exception:
        return None


def run(payload: dict, *, use_llm: bool, snapshot: dict | None = None) -> dict:
    """对一个对账/断言产物里字面不一致项逐条语义复核 + 冻结快照。

    snapshot 非空 → 可复现复核(只从快照读回,绝不调模型);为空 → 现复核
    (档位B 现复核仅用于『生成快照』一次性动作,结果即报告)。软门旁路:绝不碰主判定。
    """
    llm = _load_llm(use_llm) if snapshot is None else None
    if "results" in payload:
        kind = "oracle"
        out = review_oracle_result(payload, llm=llm, snapshot=snapshot)
    else:
        kind = "reconcile"
        out = review_reconcile_result(payload, llm=llm, snapshot=snapshot)
    block = out["xlayer_review"]
    reviews = block["reviews"]
    equivalent = sum(1 for r in reviews if r.get("status") == STATUS_OK)
    return {
        "kind": kind,
        "mode": ("snapshot" if snapshot is not None else ("B(llm)" if llm else "A(lexical)")),
        "reviewed": block["reviewed"],
        "semantic_equivalent": equivalent,
        "needs_human_review": block["reviewed"] - equivalent,
        "tier": block["tier"],
        "status": block["status"],
        "reviews": reviews,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="跨层一致性字面误报的语义复核快照(档位B,可复现,软门旁路不动 verdict)")
    ap.add_argument("--input", required=True, help="reconcile/oracle 结果 JSON(字面不一致项)")
    ap.add_argument("--llm", action="store_true",
                    help="开档位B(需 workspace 注册 xlayer_reviewer,默认降级确定性 base)")
    ap.add_argument("--from-snapshot", dest="from_snapshot",
                    help="从复核快照可复现读回(只从快照,不重调模型)")
    ap.add_argument("--output", default="xlayer-review-autogen.json")
    args = ap.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    snapshot = None
    if args.from_snapshot:
        snapshot = json.loads(Path(args.from_snapshot).read_text(encoding="utf-8"))

    report = run(payload, use_llm=args.llm, snapshot=snapshot)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"输入 {report['kind']} · 模式 {report['mode']} · 复核 {report['reviewed']} 条字面不一致")
    print(f"  疑似语义等价(semantic_equivalent) {report['semantic_equivalent']}")
    print(f"  待人审(needs_human_review) {report['needs_human_review']}")
    print("  注:软门旁路,主判定 consistent/passed 未改——真不一致仍 FAIL 暴露")
    print(f"写出:{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
