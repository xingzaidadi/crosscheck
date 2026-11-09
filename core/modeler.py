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
    spec.code_path = route.get("code_path", "") or spec.code_path

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
        spec.needs_review = ["自动建模:复用人审映射+抓包,现调接口对账,可直接执行"]
    else:
        spec.needs_review = [f"功能『{feature}』映射未人审或缺 _source 接口,补齐后转 human_verified"]


# ───────────────────────── 写入类:拼提交体/断言/清理(进阶) ─────────────────────────

def _open_ro_db(db_name: str):
    """按库名开只读连接(自发现补全用);开不了返回 None,不阻断建模。"""
    if not db_name:
        return None
    try:
        from core.config import db_params
        from db.client import DbClient
        p = db_params(db_name)
        return DbClient(readonly_params=p) if p else None
    except Exception:  # noqa: BLE001
        return None


def _is_name_key(key: str) -> bool:
    """单据『标题/名称』字段(造数唯一标记放这里)。收紧匹配,避免把 *UserName/*OrgName
    这类展示名误当标记字段而覆盖真实业务值 —— 只认标题类 + 恰为 name。"""
    low = key.lower()
    return ("title" in low or "标题" in key or "名称" in key or low == "name")


def _derive_children(db, parent_table: str, parent_key: str) -> list[str]:
    """推导清理子表:外键图(最稳,异构命名也认)∪ 同模块前缀,再都用"含父键列"收口。免人工列。"""
    if not db or not parent_table or not parent_key:
        return []
    from core.dbmap import fk_children
    prefix = parent_table.split("_")[0] + "_"   # 同模块前缀兜底
    cand: set[str] = set(fk_children(db, parent_table))   # 先 FK 图
    for t in db.tables():                                 # 再并前缀同模块
        if t != parent_table and t.startswith(prefix):
            cand.add(t)
    out = []
    for t in cand:
        if t == parent_table:
            continue
        try:
            if parent_key in db.columns(t):   # 收口:必须含父键列,才能按父单号反删
                out.append(t)
        except Exception:  # noqa: BLE001
            pass
    return sorted(out)


def _discover_complete(body: dict, table: str, db, feature: str, marker: str) -> list[str]:
    """自发现补全(A3):读库约束,把提交体里空着的『必填』字段用枚举/样例/类型兜底填上。
    同时把发现的必填字段记进自进化知识库(越跑越熟)。返回填了哪些字段(报告用)。"""
    from core.discovery.db_intel import table_constraints, sample_values
    from core.discovery.resolver import resolve_value
    from core.discovery.knowledge import FieldIntel
    from core.mapping_builder import camel_to_snake

    cons = table_constraints(db, table)
    required = [c for c, m in cons.items() if m.get("required")]
    # API 字段(camel)→ 库列(snake)对照,找出提交体里对应库必填却空着的
    body_by_snake = {camel_to_snake(k): k for k in body}
    need_cols = [c for c in required if c in body_by_snake and body.get(body_by_snake[c]) in ("", None)]
    samples = sample_values(db, table, need_cols) if need_cols else {}
    filled: list[str] = []
    intel = FieldIntel(feature)
    for col in need_cols:
        api_field = body_by_snake[col]
        enum = cons[col].get("enum") or []
        val = resolve_value({"label": api_field, "control": "text", "options": enum},
                            db_sample=samples.get(col) or None, marker=marker)
        if val not in ("", None):
            body[api_field] = val
            filled.append(api_field)
    # 记进知识库:本功能这些字段是必填(含枚举/样例),供下次秒填 + 进化
    intel.merge([{"key": body_by_snake.get(c, c), "required": True,
                  "options": cons[c].get("enum") or [],
                  "value_hint": (samples.get(c) or [None])[0]} for c in required if c in body_by_snake],
                source="db")
    intel.save()
    return filled


def _build_body(cfg: dict) -> dict:
    """从抓包模板拼请求体:去服务端字段、marker 注占位、item 去自增、body_set 覆盖特定字段。
    cfg: {template, drop_fields, item_key, item_drop, marker_fields, body_set}。
    body_set 可放 {{draftCode}} 之类占位,执行期由前置造数抓到的 vars 填入。
    inline_body(可选):直接给报文(来自 actionmap 录制的动作桩),省去外部 template 文件。"""
    import copy
    if cfg.get("inline_body") is not None:
        tpl = copy.deepcopy(cfg["inline_body"])
    else:
        tpl = json.loads(Path(cfg["template"]).read_text(encoding="utf-8"))
    drop = set(cfg.get("drop_fields") or [])
    item_key = cfg.get("item_key")
    item_drop = set(cfg.get("item_drop") or [])
    body: dict[str, Any] = {k: v for k, v in tpl.items() if k not in drop and k != item_key}
    if item_key and isinstance(tpl.get(item_key), list):
        body[item_key] = [{k: v for k, v in (it or {}).items() if k not in item_drop}
                          for it in tpl[item_key]]
    for mf in (cfg.get("marker_fields") or []):
        body[mf] = "{{marker}}"
    for k, v in (cfg.get("body_set") or {}).items():
        _set_path(body, k, v)
    return body


def _set_path(obj, dotted: str, value) -> None:
    """按点路径写值:支持嵌套与列表下标,如 'itemList.0.quantity'。中间缺省自动建 dict。
    纯通用工具(覆盖任意层字段,写入类造数常用),零业务。"""
    parts = dotted.split(".")
    cur = obj
    for i, p in enumerate(parts):
        last = i == len(parts) - 1
        idx = int(p) if p.lstrip("-").isdigit() else None
        if idx is not None and isinstance(cur, list):
            while len(cur) <= idx:
                cur.append({})
            if last:
                cur[idx] = value
            else:
                cur = cur[idx]
        else:
            if last:
                cur[p] = value
            else:
                if p not in cur or not isinstance(cur[p], (dict, list)):
                    nxt = parts[i + 1]
                    cur[p] = [] if nxt.lstrip("-").isdigit() else {}
                cur = cur[p]


def _fill_write(spec: ExecSpec, route: dict, kb_root: Path, caps_root: Path, db=None) -> None:
    """写入类自动建模:抓包模板拼提交体 + 前置造数串联 + 自发现补全必填 + 装配 approve/断言/清理。

    业务 facts 全在 route['write'](workspace):endpoint/template/marker/表/审批/清理/快照/前置造数。
    框架只做通用装配:模板去服务端字段、marker 占位、前置造数抓单号串联、库约束补空缺必填、
    声明式审批与子表父删清理。
    """
    feature = route.get("feature") or ""
    spec.feature = feature
    spec.db = route.get("db", "") or spec.db
    spec.base_url = route.get("base_url", "") or spec.base_url
    spec.session = route.get("session", "") or spec.session
    spec.code_path = route.get("code_path", "") or spec.code_path

    w = route.get("write") or {}
    endpoint = w.get("endpoint") or {}
    tpl_path = w.get("template")
    inline = w.get("inline_body")   # actionmap 录制的动作桩报文,替代外部 template 文件
    has_tpl = bool(tpl_path and Path(tpl_path).exists())
    explicit_req = w.get("request")  # 动作类(转办/退回等):主动作体直接给,不走提交模板
    main_url = endpoint.get("url") or (explicit_req or {}).get("url")
    if not main_url or not (has_tpl or inline is not None or explicit_req is not None):
        spec.needs_review = [f"写入类『{feature}』缺 write.endpoint/request 或 write.template/inline_body,补 route 后可自动建模"]
        return

    # 标记字段:显式配的 + 报文里名称/标题类字段(自动认出,造数标记放这里)
    tpl_keys = list(json.loads(Path(tpl_path).read_text(encoding="utf-8")).keys()) if has_tpl \
        else (list(inline.keys()) if isinstance(inline, dict) else [])
    marker_fields = list(w.get("marker_fields") or [])
    marker_fields += [k for k in tpl_keys if _is_name_key(k) and k not in marker_fields]

    # 前置造数:每个 data_prep 项(默认沿用主模板,可各自覆盖 template/body_set)拼出请求体 +
    # capture(抓单号/版本进 vars,供主动作/断言用 {{var}} 引用)。状态守卫/流转/编辑类的前提。
    # 直通控制键(库步骤/独立鉴权/显式体),外加:有 url 无显式 body 时默认按提交模板拼(保持既有行为)。
    # 由此"提交→审批(BPM 独立 session)→等状态翻转(db_wait)→查库拿键(db_capture)→动作"整条流水线可纯配置表达。
    preps = []
    for dp in (w.get("data_prep") or []):
        step = {k: dp[k] for k in ("method", "url", "session", "base_url",
                                   "db_wait", "db_capture", "capture") if k in dp}
        if "body" in dp:
            step["body"] = dp["body"]
        elif dp.get("url"):
            step["body"] = _build_body({"template": dp.get("template", tpl_path),
                                        "drop_fields": dp.get("drop_fields", w.get("drop_fields")),
                                        "item_key": dp.get("item_key", w.get("item_key")),
                                        "item_drop": dp.get("item_drop", w.get("item_drop")),
                                        "marker_fields": dp.get("marker_fields", marker_fields),
                                        "body_set": dp.get("body_set")})
        preps.append(step)
    spec.data_prep = preps

    body = _build_body({"template": tpl_path, "inline_body": inline,
                        "drop_fields": w.get("drop_fields"),
                        "item_key": w.get("item_key"), "item_drop": w.get("item_drop"),
                        "marker_fields": marker_fields, "body_set": w.get("body_set")})

    table = w.get("table")
    pkey, pmcol = w.get("parent_key"), w.get("parent_marker_col")
    children = w.get("cleanup_children")   # None=未配,交给 schema 自动推导
    filled: list[str] = []
    # 开一次只读库:既做自发现补全必填,又按 schema 自动推导清理子表(免人工列)
    if table:
        own_db = db or _open_ro_db(spec.db)
        if own_db is not None:
            try:
                if not explicit_req:   # 动作类主体是自定义小报文,不按库约束补全提交字段
                    filled = _discover_complete(body, table, own_db, feature, "AUTOTEST")
                if children is None and pkey:
                    children = _derive_children(own_db, table, pkey)
            except Exception as e:  # noqa: BLE001  自发现失败不阻断(模板本身可用)
                spec.needs_review = [f"自发现补全/子表推导跳过(模板已可用):{str(e)[:80]}"]
            finally:
                if db is None:
                    own_db.close()
    children = children or []

    spec.request = (dict(explicit_req) if explicit_req
                    else {"method": endpoint.get("method", "POST"), "url": endpoint["url"], "body": body})
    spec.marker_field = ""
    if w.get("approve"):
        spec.approve = w["approve"]
    if table:
        where = w.get("assert_where") or f"{pmcol or ''} = '{{{{AUTOTEST_标记值}}}}'"
        # 行数可配(默认 1):负向被拒类用 0 断言"未落库",幂等类仍为 1
        asrt = {"table": table, "where": where, "row_count": w.get("assert_row_count", 1)}
        st = w.get("assert_status") or {}
        if st.get("column"):
            asrt["fields"] = {st["column"]: st.get("value")}
        db_asserts = [asrt]
        # 额外库断言(可断任意表/字段,如子表服务端重算值);where 支持 {{AUTOTEST_标记值}}/{{draftCode}} 占位
        for extra in (w.get("extra_db_asserts") or []):
            db_asserts.append(dict(extra))
        spec.assertions = {"db": db_asserts}
    # 响应/不变量断言直通(负向被拒 rejected、幂等、全字段对账、副作用防护、事件):route 声明即生效,零业务
    for key in ("response", "idempotent", "roundtrip", "unchanged", "events"):
        if w.get(key):
            spec.assertions[key] = w[key]
    # 清理:子表按父单号删 + 主表按标记删
    cleanup = [{"table": c, "key": pkey,
                "parent": {"table": table, "key_col": pkey, "marker_col": pmcol}}
               for c in children] if (children and pkey and pmcol and table) else []
    if table and pmcol:
        cleanup.append({"table": table, "column": pmcol})
    spec.cleanup = cleanup
    spec.allowed_tables = ([table] if table else []) + children
    spec.verify_poll = w.get("verify_poll") or {}
    spec.diff_full_scan = bool(w.get("diff_full_scan", True))
    spec.verify_status = "human_verified"
    spec.needs_review = ([f"自发现补全了空缺必填字段: {filled}(已记入知识库)"] if filled
                         else ["自动建模:模板+自发现装配完成,可直接执行"])


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
