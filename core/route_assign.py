"""契约端点 → 用例候选路由自动分配(通用、零业务)。

判定链(core/readiness.py)里,unknown 用例的根因是『散文/路由都抽不到接口』。
本模块把契约端点(来自 contract_ingest / route_draft)按确定性词匹配分配给具体用例,
产出『候选路由』——补上 by_feature(按端点)↔ by_case_id(按用例)之间缺的那一跳。

铁律:
- 候选是 draft 态,绝不自动晋级、绝不制造假 ready;匹配宁缺毋滥(双门槛)。
- 零业务:领域动作词由调用方(workspace)经 keywords 传入;core 只做通用驼峰/路径分词。
- 纯函数、确定性、无 IO,便于单测与复算。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from core.readiness import CaseReadiness, norm_endpoint
from core.route_draft import endpoint_to_route

# 固定标记:供 note 加标与 scorecard 识别(通用词,非领域词)。
CONTRACT_MARKER = "contract"

# 通用停用词(非领域词):太短或无区分度的词不参与匹配。
_STOP = {"api", "id", "the", "and", "for", "get", "set", "new", "to", "of", "a", "an"}

_CAMEL = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")
_NONWORD = re.compile(r"[^0-9A-Za-z]+")


def _singular(w: str) -> str:
    """保守的复数归一(通用、非领域):items→item, categories→category。只处理常见英文尾。"""
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("ses"):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def tokens(text: str) -> set[str]:
    """文本 → 词集合:小写 + 非字母数字切 + 驼峰拆分 + 去短停用词 + 复数归一。不含任何领域词。"""
    out: set[str] = set()
    for chunk in _NONWORD.split(text or ""):
        if not chunk:
            continue
        for m in _CAMEL.findall(chunk):
            w = m.lower()
            if len(w) >= 2 and w not in _STOP:
                out.add(w)
                sing = _singular(w)
                if sing != w and len(sing) >= 2:
                    out.add(sing)
    return out


def _path_segs(path: str) -> set[str]:
    """path 末两段(去路径参数/占位)→ 词集合。/api/items/{id}/search → {items, search}。"""
    segs = [s for s in norm_endpoint(path).split("/") if s and not s.startswith("{") and ":" not in s]
    out: set[str] = set()
    for seg in segs[-2:]:
        out |= tokens(seg)
    return out


def _dto_tokens(dto: str | None) -> set[str]:
    """request_dto 去 Req/Request/DTO/VO 后缀再拆词。CreateItemReq → {create, item}。"""
    if not dto:
        return set()
    base = re.sub(r"(Request|Req|DTO|Dto|VO|Vo|Form|Param|Params)$", "", str(dto))
    return tokens(base)


def endpoint_signals(ep: dict) -> dict:
    """契约端点 → 可匹配信号。ep 来自 contract_ingest 的 ContractEndpoint.to_dict()。"""
    return {
        "path": ep.get("path") or "",
        "http": ep.get("http") or "",
        "path_segs": _path_segs(ep.get("path") or ""),
        "method_name_tokens": tokens(ep.get("method_name") or ""),
        "dto_tokens": _dto_tokens(ep.get("request_dto")),
    }


def score_case_endpoint(case_tokens: set[str], sig: dict, *,
                        extra_keywords: set[str] | None = None) -> tuple[float, list[str]]:
    """确定性加权:path 末段命中最强,方法名次之,DTO 再次,workspace 关键词加权。"""
    score = 0.0
    signals: list[str] = []
    for seg in sorted(sig.get("path_segs") or ()):
        if seg in case_tokens:
            score += 2.0
            signals.append(f"path_seg:{seg}")
    for tok in sorted(sig.get("method_name_tokens") or ()):
        if tok in case_tokens:
            score += 1.0
            signals.append(f"method_name:{tok}")
    for tok in sorted(sig.get("dto_tokens") or ()):
        if tok in case_tokens:
            score += 0.8
            signals.append(f"dto:{tok}")
    for kw in sorted(extra_keywords or ()):
        if kw in case_tokens:
            score += 1.5
            signals.append(f"keyword:{kw}")
    return score, signals


@dataclass
class RouteCandidate:
    case_id: str
    route: dict                       # 兼容 readiness.case_endpoints 的 {write:{request:{method,url,body}}}
    endpoint: str                     # "POST /api/items" 便于人审
    score: float
    signals: list[str] = field(default_factory=list)
    marker: str = CONTRACT_MARKER

    def to_dict(self) -> dict[str, Any]:
        node = dict(self.route)
        node["_candidate"] = {"score": round(self.score, 2), "signals": self.signals,
                              "endpoint": self.endpoint, "marker": self.marker, "status": "draft"}
        return node


def _case_prose(case: Any) -> str:
    parts = [getattr(case, "name", ""), getattr(case, "steps_text", ""),
             getattr(case, "expected_text", ""), getattr(case, "preconditions", ""),
             getattr(case, "notes", "")]
    return "\n".join(str(p) for p in parts if p)


def assign_routes(cases: list[Any], endpoints: list[dict], *,
                  keywords: dict[str, Any] | None = None,
                  min_score: float = 2.0, margin: float = 1.0,
                  context_prefix: str = "",
                  known_var: dict | None = None) -> list[RouteCandidate]:
    """用例 × 契约端点 → 候选路由。双门槛(绝对分 min_score + 分差 margin)保证宁缺毋滥。

    keywords:领域动作词集合(workspace 传,core 不内置);按每条用例统一加权。
    """
    extra = set()
    if keywords:
        # 支持 {词: 任意} 或 [词...] 两种形态;只取词面。
        extra = set(keywords.keys()) if isinstance(keywords, dict) else set(keywords)
    sigs = [(ep, endpoint_signals(ep)) for ep in endpoints]
    out: list[RouteCandidate] = []
    for case in cases:
        cid = getattr(case, "case_id", "") or ""
        if not cid:
            continue
        ctoks = tokens(_case_prose(case))
        scored: list[tuple[float, list[str], dict]] = []
        for ep, sig in sigs:
            s, why = score_case_endpoint(ctoks, sig, extra_keywords=extra)
            if s > 0:
                scored.append((s, why, ep))
        if not scored:
            continue
        scored.sort(key=lambda t: t[0], reverse=True)
        top_s, top_why, top_ep = scored[0]
        second = scored[1][0] if len(scored) > 1 else 0.0
        # 双门槛:绝对分够 + 显著胜出(否则有歧义,不配)。
        if top_s < min_score or (top_s - second) < margin:
            continue
        route = endpoint_to_route(top_ep, context_prefix, known_var=known_var)
        if not route:          # 只读端点等 → route_draft 返回 None,跳过
            continue
        route.setdefault("write", {}).setdefault("_contract", {})["marker"] = CONTRACT_MARKER
        endpoint = f"{top_ep.get('http','')} {top_ep.get('path','')}".strip()
        out.append(RouteCandidate(cid, route, endpoint, top_s, top_why))
    return out


def stamp_contract_note(item: CaseReadiness, candidate: RouteCandidate) -> CaseReadiness:
    """把因候选路由翻正的用例 note 改写为含 contract 标记。

    唯一确定性接缝:compute_one 的 note 硬编码、route body 传不进 note,而 scorecard
    靠 note 含 "contract" 数 zero_route。此处只写通用词 contract,不违反零业务红线。
    """
    note = f"{CONTRACT_MARKER}: {candidate.endpoint} (score={round(candidate.score, 2)}, {candidate.signals})"
    return CaseReadiness(item.case_id, item.ready, list(item.blocked_by), note)
