"""
通用自动建模器:散文用例(RawCase)→ 可执行规格(ExecSpec),尽量不靠人手写 spec。

定位(通用、与业务无关):
  - 框架只做"编排 + 复用自发现产物",不认识任何具体业务。
  - 业务侧信息全部来自 workspace:
      · 路由(用例→功能/库/站点)      workspace/config/case_routes.yaml
      · 查询映射(probe 自动建模 + 人审) workspace/knowledge_base/query_mapping/<feature>.json
      · 抓包样本(probe 产出)           workspace/captures/<feature>_picked.json
      · 自发现四来源(前端/库/文档/知识库) core/discovery/*(按站点/功能指向)
  - 换业务 = 改 workspace 的上述文件,core/ 不动。

分两条路(按 from_raw 的确定性分流):
  query/reconcile —— 复用已 probe+人审 的映射 + 抓包样本,直接拼出可跑的对账规格。
  write/api       —— 用自发现(库约束/文档/知识库)+ 抓包模板,拼出提交体/断言/清理(进阶,见 _fill_write)。

LLM 只在建模期作为"补全草稿"的可选挂钩(默认关,离线/免费可跑);执行期纯确定性。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.spec import ExecSpec, from_raw


# ───────────────────────── 路由:用例 → 功能/库/站点 ─────────────────────────

def _module_leaf(module: str) -> str:
    parts = [p for p in (module or "").replace("\\", "/").split("/") if p]
    return parts[-1] if parts else ""


def route_case(raw, routes: dict) -> dict | None:
    """把一条用例路由到一个功能配置。优先级:case_id 精确 > 模块末级 > 标题/步骤关键词。

    routes 结构(workspace/config/case_routes.yaml):
      defaults: {base_url, session, db}
      by_case_id: {CASE-1: {feature: <功能名>, db: <库名>}, ...}
      by_keyword: [{match: [列表, 检索], feature: <功能名>, db: <库名>}, ...]
    命中则返回 defaults 合并后的配置(feature 必含),否则 None。
    """
    if not routes:
        return None
    defaults = routes.get("defaults") or {}
    by_id = routes.get("by_case_id") or {}
    if raw.case_id in by_id:
        return {**defaults, **by_id[raw.case_id]}
    leaf = _module_leaf(raw.module)
    blob = f"{raw.name}\n{getattr(raw, 'steps_text', '')}\n{leaf}"
    for rule in (routes.get("by_keyword") or []):
        terms = rule.get("match") or []
        if terms and any(t in blob for t in terms):
            cfg = {k: v for k, v in rule.items() if k != "match"}
            return {**defaults, **cfg}
    return None


# ───────────────────────── 查询类:拼可跑的对账规格 ─────────────────────────

def _fill_reconcile(spec: ExecSpec, route: dict, kb_root: Path, caps_root: Path) -> None:
    """用已 probe+人审 的映射 + 抓包样本,拼出可跑的 reconcile 规格(无需人手写)。"""
    feature = route.get("feature") or ""
    spec.feature = feature
    spec.db = route.get("db", "") or spec.db
    spec.base_url = route.get("base_url", "") or spec.base_url
    spec.session = route.get("session", "") or spec.session

    mapping_path = kb_root / "query_mapping" / f"{feature}.json"
    sample_path = caps_root / f"{feature}_picked.json"

    if not mapping_path.exists():
        spec.needs_review = [f"功能『{feature}』缺人审映射 {mapping_path.name}:先 run_verify probe 并人审"]
        return
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    src = mapping.get("_source") or {}

    # 现调接口对账:url/method 取自映射 _source,请求体结构取自抓包样本并清空筛选 + 规整分页。
    # (不用样本里的旧响应 —— 那是抓包当时的库快照,会过期;现调=新 api 对新库,才是可信判据。)
    body: dict[str, Any] = {}
    if sample_path.exists():
        picked = json.loads(sample_path.read_text(encoding="utf-8"))
        body = dict(picked.get("request_body") or {})
        for k in list(body):
            kl = k.lower()
            if kl in ("pagenum", "pageno"):
                body[k] = 1
            elif kl in ("pagesize", "size", "limit"):
                body[k] = 10
            elif isinstance(body[k], list):
                body[k] = []
            elif isinstance(body[k], str):
                body[k] = ""
            elif isinstance(body[k], (int, float)) and kl not in ("pagenum", "pageno", "pagesize", "size", "limit"):
                body[k] = ""
    if src.get("url"):
        spec.request = {"method": src.get("method", "POST"), "url": src["url"], "body": body}

    # 映射人审 + 有可现调的接口 → 可跑;对账自证一致,无需额外断言
    if mapping.get("verify_status") == "human_verified" and spec.request:
        spec.verify_status = "human_verified"
    else:
        spec.needs_review = [f"功能『{feature}』映射未人审或缺 _source 接口,补齐后转 human_verified"]


# ───────────────────────── 写入类:拼提交体/断言/清理(进阶) ─────────────────────────

def _fill_write(spec: ExecSpec, route: dict, kb_root: Path, caps_root: Path, db=None) -> None:
    """写入类自动建模:用抓包模板 + 自发现(库约束/文档/知识库)拼提交体/断言/清理。

    当前实现:若路由给了 template(抓包模板文件)与清理/断言配置,则据此拼装;
    否则留 draft 并标注(待自发现/LLM 补全)。自发现接入点见 core/discovery/*。
    """
    feature = route.get("feature") or ""
    spec.feature = feature
    spec.db = route.get("db", "") or spec.db
    spec.base_url = route.get("base_url", "") or spec.base_url
    spec.session = route.get("session", "") or spec.session
    spec.needs_review = [f"写入类『{feature}』自动建模待接入自发现(库约束/文档/知识库)+ LLM 草拟提交体/断言"]


# ───────────────────────── 对外:建模一条 / 一批 ─────────────────────────

def model_case(raw, *, routes: dict, kb_root: Path, caps_root: Path, db=None) -> ExecSpec:
    """一条散文用例 → ExecSpec。先确定性分流,再按路由复用自发现产物补成可跑规格。

    路由优先:命中路由的功能若有 query_mapping 则按对账建模(路由是人工配的业务信息,
    比 from_raw 的关键词猜测更可靠,避免"列表"用例因预期里含'提交/审批'被误判成写入)。
    路由可用 mode: reconcile|write 显式指定,覆盖自动判断。
    """
    spec = from_raw(raw)
    route = route_case(raw, routes)
    if route is None:
        spec.needs_review = [f"未命中路由(workspace/config/case_routes.yaml):{_module_leaf(raw.module)} / {raw.name[:30]}"]
        return spec

    feature = route.get("feature") or ""
    has_mapping = (kb_root / "query_mapping" / f"{feature}.json").exists()
    mode = route.get("mode") or ("reconcile" if has_mapping else "write")
    if mode == "reconcile":
        spec.kind, spec.mode = "query", "reconcile"
        _fill_reconcile(spec, route, kb_root, caps_root)
    else:
        spec.kind, spec.mode = "write", "api"
        _fill_write(spec, route, kb_root, caps_root, db)
    return spec


def model_cases(raws, *, routes: dict, kb_root: Path, caps_root: Path, db=None) -> list[ExecSpec]:
    return [model_case(r, routes=routes, kb_root=kb_root, caps_root=caps_root, db=db) for r in raws]


def load_routes(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    import yaml
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
