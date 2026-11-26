"""CP-1 语义复核 checker(档位A:确定性词法覆盖,零业务、纯函数)。

三段式里 CP-1 的结构门 validate_spec() 只管"字段齐不齐";本模块补它管不了的那层——
**转出来的操作是否忠实于用例原意**。做法是把用例原文(exec_spec.raw 自带的
steps/expected)与转出的操作(ui/assertions/request/endpoints/steps)做词法覆盖比对,
给出覆盖率 + 缺口清单。

铁律:
- 软门:checker 只产 spec_review 候选(status=needs_human_review / semantic_ok),
  绝不改 exec_spec、绝不自动打回;最终信不信由人审。
- 零业务:不内置任何业务动作词典;覆盖口径全走"用例原文词集 vs spec 词集"的通用分词
  (复用 core.route_assign.tokens 的驼峰/复数归一),业务事实由用例文本派生。
- 纯函数、确定性、无 IO,便于单测与复算。
- 档位B(LLM 语义复核)留 produce() 的接口位,无模型时自动降级到本档位A,不阻塞。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.route_assign import tokens

# spec 段的旁路产物键(checker 专属;maker 写 exec_spec,checker 写 spec_review,互不越界)。
REVIEW_ARTIFACT = "spec_review"

# 软门状态值(通用词,非业务词)。
STATUS_OK = "semantic_ok"
STATUS_REVIEW = "needs_human_review"

# 只读/不触发写的 mode(通用框架词);用例原文覆盖到 spec 的动作里却落只读 mode 时提示存疑。
_READONLY_MODES = {"reconcile", "api", "manual"}


def _prose_tokens(spec: dict) -> set[str]:
    """用例原文词集:steps(怎么做)+ expected(预期)+ title。原文来自 exec_spec.raw 自带副本。"""
    raw = spec.get("raw") or {}
    blob = "\n".join(str(raw.get(k, "")) for k in ("steps", "expected")) + "\n" + str(spec.get("title", ""))
    return tokens(blob)


def _expected_tokens(spec: dict) -> set[str]:
    """用例预期词集:只取 expected(用于判断"预期是否进了断言")。"""
    raw = spec.get("raw") or {}
    return tokens(str(raw.get("expected", "")))


def _spec_action_tokens(spec: dict) -> set[str]:
    """转出的"操作"词集:ui(指令/动作/页面)+ request(主写动作)+ endpoints + steps。"""
    out: set[str] = set()
    ui = spec.get("ui") or {}
    out |= tokens(str(ui.get("instruction", "")))
    out |= tokens(str(ui.get("page_url", "")))
    for action in ui.get("actions") or []:
        out |= tokens(str(action if not isinstance(action, dict)
                          else action.get("target") or action.get("selector") or action.get("kind") or ""))
    req = spec.get("request") or {}
    out |= tokens(str(req.get("url", "")))
    out |= tokens(str(req.get("method", "")))
    for ep in spec.get("endpoints") or []:
        out |= tokens(str(ep))
    for step in spec.get("steps") or []:
        out |= tokens(str(step if not isinstance(step, dict) else step.get("kind") or step.get("url") or ""))
    return out


def _spec_assertion_tokens(spec: dict) -> set[str]:
    """转出的"判定依据"词集:assertions(响应/库校验)的键与值路径。"""
    out: set[str] = set()
    assertions = spec.get("assertions") or {}
    out |= _walk_tokens(assertions)
    return out


def _walk_tokens(obj: Any) -> set[str]:
    """递归把 dict/list 的键和标量值拆成词(用于 assertions/body 这类嵌套结构)。"""
    out: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            out |= tokens(str(k))
            out |= _walk_tokens(v)
    elif isinstance(obj, list):
        for item in obj:
            out |= _walk_tokens(item)
    elif obj not in (None, "", True, False):
        out |= tokens(str(obj))
    return out


def review_spec(exec_spec: dict, *, min_coverage: float = 0.5) -> dict:
    """语义词法复核:用例原意 vs 转出操作的覆盖比对。返回 spec_review 内容(不含外层键)。

    通过(semantic_ok)条件:
      - 动作覆盖率 >= min_coverage(用例原文动作词有足够比例落进了 spec 的操作/断言);
      - 预期有着落(expected 词集与 assertions∪ui 有交集,或用例本就无显式预期);
      - mode 合理(用例原文动作词进了 spec 操作,却落只读 mode → 存疑,不直接否);
    任一不满足 → needs_human_review + 具体缺口清单。纯覆盖口径,零业务。
    """
    prose = _prose_tokens(exec_spec)
    act_toks = _spec_action_tokens(exec_spec)
    assert_toks = _spec_assertion_tokens(exec_spec)
    covered = act_toks | assert_toks

    reasons: list[str] = []

    # 1) 动作覆盖:用例原文词里有多少被 spec 的操作/断言覆盖
    hit = prose & covered
    coverage = round(len(hit) / len(prose), 4) if prose else 1.0
    missing = sorted(prose - covered)[:20]
    if prose and coverage < min_coverage:
        reasons.append(f"动作覆盖不足:用例 {len(prose)} 词仅 {len(hit)} 词落进操作/断言"
                       f"(coverage={coverage:.0%} < {min_coverage:.0%})")

    # 2) 预期对齐:用例的预期词是否进了断言或 ui
    exp = _expected_tokens(exec_spec)
    if exp:
        ui_toks = _spec_action_tokens(exec_spec)
        if not (exp & (assert_toks | ui_toks)):
            reasons.append("预期未对齐:用例 expected 的判定点未出现在 assertions/ui 中")

    # 3) mode 合理性:用例原文明显驱动了操作(有动作命中),却落在只读/不触发写的 mode
    mode = str(exec_spec.get("mode", ""))
    has_write_request = bool((exec_spec.get("request") or {}).get("url"))
    if hit and mode in _READONLY_MODES and not has_write_request and not (exec_spec.get("ui") or {}):
        reasons.append(f"mode 存疑:用例含操作词但 mode={mode!r} 不触发写且无 ui 计划,可能转成了只读核对")

    # 4) 臆造检测:断言/请求体里的字段词,是否在用例原文里有出处
    body = (exec_spec.get("request") or {}).get("body") or {}
    body_toks = _walk_tokens(body) | assert_toks
    fabricated = sorted(body_toks - prose)
    # 只在断言/请求体非空、且全部字段词都是用例没提过的词时提示(避免对通用结构词误报)
    if body_toks and len(fabricated) == len(body_toks) and len(body_toks) >= 3:
        reasons.append(f"疑似臆造:assertions/request.body 的字段词在用例原文里均无出处 {fabricated[:8]}")

    status = STATUS_OK if not reasons else STATUS_REVIEW
    return {
        "status": status,
        "tier": "lexical",            # 档位A;档位B 为 "llm"
        "coverage": coverage,
        "missing": missing,           # 用例要求了但 spec 没覆盖的词(给人审看"漏了啥")
        "reasons": reasons,
        "prose_terms": len(prose),
        "covered_terms": len(hit),
    }


def freeze_review(case_id: str, review: dict) -> dict:
    """把一次(档位B)语义复核结果冻结成快照条目——判定与模型调用物理隔离的铁律载体。

    快照是唯一真相源:生成时(SPEC_LLM=1)真调一次模型写进快照,之后判定只从快照
    确定性读回(review_from_snapshot),绝不重调模型——守『可复现』铁律(照搬 oracle 档位B)。
    """
    return {
        "case_id": str(case_id),
        "tier": str(review.get("tier") or "llm"),
        "status": str(review.get("status") or STATUS_REVIEW),
        "faithful": bool(review.get("faithful", review.get("status") == STATUS_OK)),
        "reasons": list(review.get("reasons") or []),
        "semantic_gaps": list(review.get("semantic_gaps") or []),
    }


def _snapshot_index(snapshot: Any) -> dict[str, dict]:
    """把快照(数组或 {case_id→条目})归一成 case_id→冻结条目 的索引。"""
    index: dict[str, dict] = {}
    rows = snapshot.get("reviews", snapshot) if isinstance(snapshot, dict) else snapshot
    if isinstance(rows, dict):
        for cid, row in rows.items():
            if isinstance(row, dict):
                index[str(cid)] = row
    elif isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and row.get("case_id"):
                index[str(row["case_id"])] = row
    return index


def review_from_snapshot(exec_spec: dict, snapshot_index: dict[str, dict],
                         *, min_coverage: float = 0.5) -> dict:
    """可复现判定:只从冻结快照读回档位B 结果,绝不调模型。

    档位A 的覆盖证据(coverage/missing)仍现算保留;快照缺该 case → 整体降级档位A。
    """
    base = review_spec(exec_spec, min_coverage=min_coverage)   # 档位A 证据(确定性)
    case_id = str(exec_spec.get("case_id") or "")
    frozen = snapshot_index.get(case_id)
    if not frozen:
        return base                                            # 快照无此 case → 纯档位A
    merged = dict(base)
    merged["tier"] = "llm"
    merged["status"] = str(frozen.get("status") or base["status"])
    merged["faithful"] = bool(frozen.get("faithful", merged["status"] == STATUS_OK))
    # 档位B 的语义理由叠加在档位A 词法理由之上(人审能同时看到两档依据)
    merged["reasons"] = list(base.get("reasons") or []) + list(frozen.get("reasons") or [])
    merged["semantic_gaps"] = list(frozen.get("semantic_gaps") or [])
    return merged


@dataclass
class SpecChecker:
    """CP-1 语义复核子 Agent:读 exec_spec(含原文副本)→ 产 spec_review 候选。

    与 maker(SpecAgent)分离:maker 只能写 exec_spec,checker 只能写 spec_review
    (由 stage_runner.enforce_write_scope 的旁路白名单强制),互不改对方产物。

    判定优先级(守可复现):
      - snapshot 在场 → review_from_snapshot(只读快照,绝不调模型)=可复现判定;
      - 否则 llm 可用 → 实时档位B(仅"生成快照"那一次性离线动作用);
      - 都无 → 档位A 词法覆盖(tier=lexical),逐位同历史现状。
    """
    min_coverage: float = 0.5
    llm: Any = None               # 档位B provider(registry 取);None=无实时档位B
    snapshot: Any = None          # case_id→冻结条目 索引;在场即走可复现判定

    def produce(self, stage: str, context: Any) -> dict[str, Any]:
        exec_spec = context.upstream_artifact("spec")
        if self.snapshot:
            review = review_from_snapshot(exec_spec, _snapshot_index(self.snapshot),
                                          min_coverage=self.min_coverage)
        elif self.llm is not None and not isinstance(self.llm, str):
            review = self._review_live(exec_spec)
        else:
            review = review_spec(exec_spec, min_coverage=self.min_coverage)
        return {REVIEW_ARTIFACT: review}

    def _review_live(self, exec_spec: dict) -> dict:
        """实时档位B:调 provider 做语义复核,叠加在档位A 证据上。

        仅用于"生成快照"的一次性离线动作(结果须经 freeze_review 冻结方可复现)。
        provider 不可用/返回空 → 纯档位A 降级(离线/零成本铁律)。
        """
        base = review_spec(exec_spec, min_coverage=self.min_coverage)
        raw = (exec_spec.get("raw") or {})
        verdict = self._invoke(provider=self.llm, context={
            "case_id": str(exec_spec.get("case_id") or ""),
            "steps": str(raw.get("steps") or ""),
            "expected": str(raw.get("expected") or ""),
            "title": str(exec_spec.get("title") or ""),
            "ui": exec_spec.get("ui") or {},
            "request": exec_spec.get("request") or {},
            "endpoints": exec_spec.get("endpoints") or [],
            "assertions": exec_spec.get("assertions") or {},
        })
        if not isinstance(verdict, dict):
            return base                                        # 降级档位A
        status = str(verdict.get("status") or "")
        if status not in {STATUS_OK, STATUS_REVIEW}:
            status = STATUS_OK if verdict.get("faithful") else STATUS_REVIEW
        merged = dict(base)
        merged["tier"] = "llm"
        merged["status"] = status
        merged["faithful"] = bool(verdict.get("faithful", status == STATUS_OK))
        merged["reasons"] = list(base.get("reasons") or []) + list(verdict.get("reasons") or [])
        merged["semantic_gaps"] = list(verdict.get("semantic_gaps") or [])
        return merged

    @staticmethod
    def _invoke(*, provider: Any, context: dict) -> Any:
        """调 provider(registry 可调用对象或带 .review 方法);任何异常→None 降级。"""
        try:
            if callable(provider):
                return provider(**context)
            review = getattr(provider, "review", None)
            return review(**context) if callable(review) else None
        except Exception:        # noqa: BLE001 —— 软门第二档不得拖垮主流程
            return None
