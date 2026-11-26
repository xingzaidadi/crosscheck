"""就绪门禁(通用、零业务):机器判定每条用例"能不能自动执行、卡在哪",
取代逐条手工撞墙。核心逻辑是跨源比对——不认识任何业务,只按通用信号判断:

一条用例要动的接口(来自路由或散文里抽的 endpoint),比对两张自发现的能力图:
  - reachable:当前已持有的登录态/角色实际够得到的接口集(rolemap 产出的并集)
  - catalog :系统里存在过的接口集(apimap 产出)
判定:
  - 已有人审路由且可建模  → ready(直接能跑)
  - 需要的接口在 reachable 里 → ready
  - 接口在 catalog 但不在 reachable → blocked_by: role(存在但当前角色够不到:缺角色账号)
  - 接口系统里都没见过      → blocked_by: action-body(从未被触发/录制,缺真实报文)
  - 规则本身未定义(标记)    → blocked_by: rule
  - 以上都判不了            → unknown(交回关键词兜底,不强判)

event/scene/file 等阻塞由后续 eventmap/envmap/fixtures 阶段补充,这里先不臆断。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

_PATH = re.compile(r"/[A-Za-z0-9_\-]+(?:/[A-Za-z0-9_\-{}]+)+")


def norm_endpoint(ep: str) -> str:
    """规整成纯 path(去域名、去查询串、去花括号参数),便于跨源比对。"""
    if not ep:
        return ""
    ep = ep.strip()
    ep = re.sub(r"^https?://[^/]+", "", ep)      # 去域名
    ep = ep.split("?", 1)[0].split("#", 1)[0]    # 去 query/fragment
    ep = re.sub(r"\{[^}]*\}", "", ep)            # 去 {param}
    return ep.rstrip("/")


def _endpoints_from_text(text: str) -> set[str]:
    return {norm_endpoint(m) for m in _PATH.findall(text or "") if "api" in m.lower()}


@dataclass
class CaseReadiness:
    case_id: str
    ready: bool
    blocked_by: list[str] = field(default_factory=list)
    note: str = ""


@dataclass
class Capabilities:
    """自发现产物汇总(都已规整为纯 path 的集合)。"""
    reachable: set[str] = field(default_factory=set)        # 当前角色实际够得到的接口(rolemap 并集)
    catalog: set[str] = field(default_factory=set)          # 系统存在过的接口(apimap)
    verified_cases: set[str] = field(default_factory=set)   # 已有人审可跑规格的 case_id
    rule_undefined: set[str] = field(default_factory=set)   # 规则待确认的 case_id


def case_endpoints(case_id: str, prose: str, route: dict | None) -> set[str]:
    """一条用例要动的接口:优先路由里显式配的(write.endpoint / request / approve / data_prep / _source),
    否则从散文里抽。注:动作类路由(转办/退回/关闭…)主接口放在 write.request,必须一并识别,
    否则明明已路由可跑的用例会被误判成『未识别到接口』。"""
    eps: set[str] = set()
    r = route or {}
    w = r.get("write") or {}
    nodes = [w.get("endpoint"), w.get("request"), w.get("approve")] + list(w.get("data_prep") or [])
    for node in nodes:
        if isinstance(node, dict) and node.get("url"):
            eps.add(norm_endpoint(node["url"]))
    src = ((r.get("_source") or {}) if isinstance(r, dict) else {})
    if src.get("url"):
        eps.add(norm_endpoint(src["url"]))
    if not eps:
        eps = _endpoints_from_text(prose)
    return {e for e in eps if e}


def compute_one(case_id: str, prose: str, route: dict | None, caps: Capabilities) -> CaseReadiness:
    if case_id in caps.rule_undefined:
        return CaseReadiness(case_id, False, ["rule"], "规则未定义,无处可探")
    if case_id in caps.verified_cases:
        return CaseReadiness(case_id, True, [], "已有可跑规格")
    eps = case_endpoints(case_id, prose, route)
    if not eps:
        return CaseReadiness(case_id, False, [], "unknown:未识别到接口,交关键词兜底")
    if eps & caps.reachable:
        return CaseReadiness(case_id, True, [], f"接口可达: {sorted(eps & caps.reachable)[:2]}")
    if eps & caps.catalog:
        return CaseReadiness(case_id, False, ["role"], "接口存在但当前角色够不到(缺角色账号)")
    return CaseReadiness(case_id, False, ["action-body"], "接口从未在流量里出现(缺真实报文/触发)")


def _case_field(c: Any, *names: str) -> str:
    """从用例里取一个文本字段,兼容两种载体:
      - 对象(RawCase):属性 .name/.steps_text/...
      - dict(load_suite 产物):顶层键,或嵌套在 actions/assertions 下的 source_text。
    任一命名命中即返回;都没有则空串。不认任何业务语义。"""
    if isinstance(c, dict):
        for n in names:
            if n in c and isinstance(c[n], str) and c[n]:
                return c[n]
            # dict 用例把散文放在 actions.source_text / assertions.source_text
            for sec in ("actions", "assertions"):
                sub = c.get(sec)
                if isinstance(sub, dict) and n in sub and isinstance(sub[n], str) and sub[n]:
                    return sub[n]
        return ""
    for n in names:
        v = getattr(c, n, "")
        if v:
            return str(v)
    return ""


def _case_prose(c: Any) -> str:
    """拼一条用例的全部可检索散文,兼容对象与 dict 两种载体。"""
    return "\n".join([
        _case_field(c, "name", "title"),
        _case_field(c, "steps_text", "source_text"),      # dict: actions.source_text
        _case_field(c, "expected_text"),                   # dict: assertions.source_text(经 actions 落空后由下一项兜)
        _case_field(c, "assertions_text", "source_text"),  # 冗余兜底:断言散文
        _case_field(c, "preconditions"),
        _case_field(c, "notes"),
    ])


def compute_readiness(cases: list[Any], caps: Capabilities,
                      routes: dict | None = None) -> list[CaseReadiness]:
    """cases: 用例集合,元素可为 RawCase 对象或 load_suite 返回的 dict。
    routes: by_case_id 路由表(可选);逐条算就绪。
    注:dict 用例的接口字面量多在 actions.source_text,必须从该字段抽,
    否则所有 dict 用例会因读空散文被误判 unknown(历史 getattr-on-dict 缺陷)。"""
    by_id = (routes or {}).get("by_case_id") or {}
    out = []
    for c in cases:
        cid = _case_field(c, "case_id") or ""
        prose = _case_prose(c)
        out.append(compute_one(cid, prose, by_id.get(cid), caps))
    return out


def write_readiness(path: str | Path, items: list[CaseReadiness]) -> None:
    import yaml
    data = {it.case_id: {"ready": it.ready, "blocked_by": it.blocked_by, "note": it.note} for it in items}
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=True), encoding="utf-8")


def load_readiness(path: str | Path) -> dict[str, dict]:
    import yaml
    p = Path(path)
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
