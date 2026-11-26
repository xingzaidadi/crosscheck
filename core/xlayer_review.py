"""跨层一致性语义复核(xlayer 档位B,软门旁路,零业务)。

crosscheck 的跨层一致性判定(reconciler 接口↔库对账、oracle 断言)是**字面/严格值比对**:
接口返回 camelCase/枚举码(COMPLETED)/ISO 时间,库是 snake_case/中文状态(已完成)/DB 时间戳,
『语义等价但字面不等』处系统性误报 false mismatch。本模块补这层——判"接口值与库值是否语义等价"。

铁律(照搬 spec_checker 档位B,一处不破):
- **软门旁路·不动 verdict**:只产 xlayer_review 候选 + 标"疑似语义等价·待人审",
  **绝不改 ReconcileResult.consistent / oracle.passed**。真不一致仍 FAIL 暴露,不被 LLM 和稀泥救回。
- **可复现**:LLM 判定天然不可复现 → 生成时真调一次冻进快照,判定只从冻结快照确定性读回,
  绝不重调模型。模型调用与判定物理隔离。
- **默认离线零成本**:llm/snapshot 皆 None → 确定性降级(默认 needs_human_review,**不臆断等价**),
  逐位同现状;core 零网络零新依赖。
- **零业务**:prompt/判定不内置业务词典;真实 LLM 客户端在 workspace/plugins/xlayer_reviewer.py 注册。
"""
from __future__ import annotations

from typing import Any

# 旁路产物键(xlayer 专属;与 reconcile.json/oracle_results 平级,绝不写 consistent/passed)。
XLAYER_REVIEW = "xlayer_review"

# 软门状态值(通用词,非业务词)。
STATUS_OK = "semantic_equivalent"
STATUS_REVIEW = "needs_human_review"


def _mismatch_key(mismatch: dict) -> str:
    """差异定位串:主键 + 字段(或断言 subject),作为快照索引键。"""
    pk = mismatch.get("pk")
    field = mismatch.get("field") or mismatch.get("subject") or ""
    return f"{pk}::{field}" if pk is not None else str(field)


def _base_review(mismatch: dict) -> dict:
    """确定性 base:字面已判不等 → 默认待人审(不臆断等价)。tier=lexical。"""
    return {
        "key": _mismatch_key(mismatch),
        "tier": "lexical",
        "status": STATUS_REVIEW,
        "semantic_equivalent": False,
        "api_value": mismatch.get("api", mismatch.get("actual")),
        "db_value": mismatch.get("db", mismatch.get("expected")),
        "field": mismatch.get("field") or mismatch.get("subject") or "",
        "reasons": [],
    }


def freeze_review(key: str, review: dict) -> dict:
    """把一次(档位B)语义复核结果冻成快照条目——判定与模型调用物理隔离的铁律载体。

    快照是唯一真相源:生成时(XLAYER_LLM=1)真调一次模型写进快照,之后判定只从快照
    确定性读回(review_from_snapshot),绝不重调模型(照搬 spec_checker.freeze_review)。
    """
    return {
        "key": str(key),
        "tier": str(review.get("tier") or "llm"),
        "status": str(review.get("status") or STATUS_REVIEW),
        "semantic_equivalent": bool(review.get("semantic_equivalent",
                                               review.get("status") == STATUS_OK)),
        "reasons": list(review.get("reasons") or []),
    }


def _snapshot_index(snapshot: Any) -> dict[str, dict]:
    """把快照(数组或 {key→条目})归一成 key→冻结条目 索引(照搬 spec_checker)。"""
    index: dict[str, dict] = {}
    rows = snapshot.get("reviews", snapshot) if isinstance(snapshot, dict) else snapshot
    if isinstance(rows, dict):
        for k, row in rows.items():
            if isinstance(row, dict):
                index[str(k)] = row
    elif isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and row.get("key"):
                index[str(row["key"])] = row
    return index


def review_from_snapshot(mismatch: dict, snapshot_index: dict[str, dict]) -> dict:
    """可复现判定:只从冻结快照读回档位B 结果,绝不调模型。

    快照缺该 key → 降级确定性 base(tier=lexical,待人审),不臆断等价。
    """
    base = _base_review(mismatch)
    frozen = snapshot_index.get(base["key"])
    if not frozen:
        return base
    merged = dict(base)
    merged["tier"] = str(frozen.get("tier") or "llm")
    merged["status"] = str(frozen.get("status") or base["status"])
    merged["semantic_equivalent"] = bool(frozen.get("semantic_equivalent",
                                                     merged["status"] == STATUS_OK))
    merged["reasons"] = list(frozen.get("reasons") or [])
    return merged


def _invoke(*, provider: Any, context: dict) -> Any:
    """调 provider(registry 可调用对象或带 .review 方法);任何异常→None 降级。

    软门第二档不得拖垮主流程(照搬 spec_checker._invoke)。
    """
    try:
        if callable(provider):
            return provider(**context)
        review = getattr(provider, "review", None)
        return review(**context) if callable(review) else None
    except Exception:        # noqa: BLE001
        return None


def _review_live(mismatch: dict, provider: Any) -> dict:
    """实时档位B:调 provider 判语义等价。仅用于"生成快照"的一次性离线动作。

    provider 不可用/返回空 → 确定性 base 降级(离线/零成本铁律)。
    """
    base = _base_review(mismatch)
    verdict = _invoke(provider=provider, context={
        "field": base["field"],
        "api_value": base["api_value"],
        "db_value": base["db_value"],
        "pk": mismatch.get("pk"),
    })
    if not isinstance(verdict, dict):
        return base
    status = str(verdict.get("status") or "")
    equivalent = bool(verdict.get("semantic_equivalent", status == STATUS_OK))
    if status not in {STATUS_OK, STATUS_REVIEW}:
        status = STATUS_OK if equivalent else STATUS_REVIEW
    merged = dict(base)
    merged["tier"] = "llm"
    merged["status"] = status
    merged["semantic_equivalent"] = equivalent
    merged["reasons"] = [str(r) for r in (verdict.get("reasons") or []) if str(r).strip()]
    return merged


def review_mismatch(mismatch: dict, *, llm: Any = None,
                    snapshot_index: dict[str, dict] | None = None) -> dict:
    """对单条字面已判不一致的跨层差异做语义复核。判定优先级(守可复现):
      - snapshot_index 在场 → review_from_snapshot(只读快照,绝不调模型);
      - 否则 llm 可用(非 None、非 str)→ _review_live(实时档位B,仅生成快照用);
      - 都无 → 确定性 base(tier=lexical,待人审,不臆断等价)。
    """
    if snapshot_index is not None:
        return review_from_snapshot(mismatch, snapshot_index)
    if llm is not None and not isinstance(llm, str):
        return _review_live(mismatch, llm)
    return _base_review(mismatch)


def _fold(reviews: list[dict]) -> dict:
    """把逐条复核折成旁路产物:全部语义等价→semantic_equivalent;有待人审→needs_human_review。"""
    tier = "llm" if any(r.get("tier") == "llm" for r in reviews) else "lexical"
    status = STATUS_OK if reviews and all(r.get("status") == STATUS_OK for r in reviews) else STATUS_REVIEW
    return {XLAYER_REVIEW: {"reviews": reviews, "status": status, "tier": tier,
                            "reviewed": len(reviews)}}


def review_reconcile_result(result: dict, *, llm: Any = None,
                            snapshot: Any = None) -> dict:
    """对 ReconcileResult(dict 形态)的字面不一致项逐条语义复核。

    只看 field_samples 里 ok==False 的样本(接口值 vs 库值字面不等)。
    **绝不读写 consistent**——软门旁路,主判定不动。返回 {XLAYER_REVIEW: {...}}。
    """
    snap_index = _snapshot_index(snapshot) if snapshot is not None else None
    reviews: list[dict] = []
    for sample in result.get("field_samples") or []:
        if sample.get("ok") is False:
            reviews.append(review_mismatch(sample, llm=llm, snapshot_index=snap_index))
    return _fold(reviews)


def review_oracle_result(oracle_result: dict, *, llm: Any = None,
                         snapshot: Any = None) -> dict:
    """对 oracle.evaluate 结果里 passed==False 的断言逐条语义复核。

    **绝不读写 passed/failed**——软门旁路,主判定不动。返回 {XLAYER_REVIEW: {...}}。
    """
    snap_index = _snapshot_index(snapshot) if snapshot is not None else None
    reviews: list[dict] = []
    for item in oracle_result.get("results") or []:
        if item.get("passed") is False:
            reviews.append(review_mismatch(item, llm=llm, snapshot_index=snap_index))
    return _fold(reviews)
