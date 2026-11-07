"""
表格结构探测(前置操作·通用):给一个列表/明细页,自动产出 UI 断言要用的
`ui.extract`(rows_selector + 列 nth-child 映射)和 `dom_to_api`,免去人手扒选择器。

关键做法(零业务、语言无关):
  1) 选数据表:组件库常把一张表拆成 表头表/表体表/固定列表 多个 <table>,页面上还有
     日期选择器日历表。选"表体"那张——wrapper 含 'table-body',或 tbody 行数等于接口返回条数,
     排除 wrapper 含 'date-picker'/'calendar' 的噪音表。
  2) 列映射:非空表头按位置 → td:nth-child(i)(1 基)。
  3) dom_to_api:不靠中文字典,靠**值相等**——某列第一行的显示值 == 接口首行某字段的值,
     就把这列映射到那个字段。数值做归一(1 == 1.0)。

纯函数 build_extract 可离线测;probe() 用 Playwright 实开页面取证。
"""
from __future__ import annotations

import re

_NOISE_WRAP = ("date-picker", "calendar", "picker__calendar")


def _norm(v) -> str:
    s = str(v).strip()
    m = re.fullmatch(r"-?\d+(?:\.\d+)?", s)
    if m:
        f = float(s)
        return str(int(f)) if f == int(f) else str(f)
    return s


def pick_data_table(tables: list[dict], api_len: int | None = None) -> int:
    """tables: [{wrapper, headers:[str], row0:[str], rows:int}] → 数据表下标。"""
    cands = [i for i, t in enumerate(tables)
             if not any(n in (t.get("wrapper") or "").lower() for n in _NOISE_WRAP)]
    if not cands:
        cands = list(range(len(tables)))
    # 1) wrapper 明确是表体
    body = [i for i in cands if "table-body" in (tables[i].get("wrapper") or "").lower()
            and tables[i].get("rows", 0) > 0]
    if body:
        return body[0]
    # 2) 行数等于接口条数
    if api_len:
        exact = [i for i in cands if tables[i].get("rows") == api_len]
        if exact:
            return exact[0]
    # 3) 有表头且数据行最多的那张
    withrows = [i for i in cands if tables[i].get("rows", 0) > 0 and any(tables[i].get("headers") or [])]
    if withrows:
        return max(withrows, key=lambda i: tables[i].get("rows", 0))
    return cands[0]


def build_columns(headers: list[str]) -> dict:
    """非空表头 → {slug: 'td:nth-child(i)'}(1 基,空表头列跳过,如前导复选框列)。"""
    cols = {}
    for i, h in enumerate(headers, start=1):
        h = (h or "").strip()
        if not h:
            continue
        slug = re.sub(r"\s+", "", h)
        cols[slug] = f"td:nth-child({i})"
    return cols


def match_dom_to_api(headers: list[str], row0: list[str], api_row: dict) -> dict:
    """靠值相等把 DOM 列(表头slug)映射到接口字段:row0[i] 的值 == api_row[k] 的值。"""
    api_norm = {k: _norm(v) for k, v in (api_row or {}).items() if not isinstance(v, (dict, list))}
    out, used = {}, set()
    for i, h in enumerate(headers):
        h = (h or "").strip()
        if not h or i >= len(row0):
            continue
        dv = _norm(row0[i])
        if dv == "" or dv == "-":
            continue
        slug = re.sub(r"\s+", "", h)
        for k, v in api_norm.items():
            # 不复用已绑字段:两列同值(如两列都显示同一个人)时,后一列留空待人审,不乱绑
            if v != "" and v == dv and k not in used:
                out[slug] = k
                used.add(k)
                break
    return out


def _headers_for(tables: list[dict], data_idx: int) -> list[str]:
    """数据表自身有表头就用它;否则(组件库表头/表体分表)去同组 'table-header' 表取表头。"""
    own = [h for h in (tables[data_idx].get("headers") or []) if (h or "").strip()]
    if own:
        return tables[data_idx]["headers"]
    for i, t in enumerate(tables):
        if i == data_idx:
            continue
        if "table-header" in (t.get("wrapper") or "").lower() and any((t.get("headers") or [])):
            return t["headers"]
    return tables[data_idx].get("headers") or []


def _scope_selector(wrapper: str) -> str:
    """从数据表 wrapper 的 class 列表里挑一个最能定位表体的类,拼成收窄选择器。
    通用:优先含 'table-body' 的类,否则第一个含 'table' 的类;都没有则退回全表。"""
    classes = [c for c in (wrapper or "").split() if c]
    body = [c for c in classes if "table-body" in c.lower()]
    tbl = body or [c for c in classes if "table" in c.lower()]
    return f".{tbl[0]} tbody tr" if tbl else "table tbody tr"


def build_extract(tables: list[dict], api_rows: list[dict], *,
                  api_rows_path: str = "data.records",
                  body_wrapper_selector: str | None = None) -> dict:
    """汇总:选数据表 + 列映射 + dom_to_api → 可直接塞进 UI spec 的 ui.extract 配置。
    rows_selector 默认从探到的数据表 wrapper 自动推导(零硬编码);也可显式覆盖。"""
    idx = pick_data_table(tables, api_len=len(api_rows) if api_rows else None)
    t = tables[idx]
    headers = _headers_for(tables, idx)
    row0 = t.get("row0") or []
    cols = build_columns(headers)
    d2a = match_dom_to_api(headers, row0, api_rows[0] if api_rows else {})
    rows_selector = (f"{body_wrapper_selector} tbody tr" if body_wrapper_selector
                     else _scope_selector(t.get("wrapper") or ""))
    return {
        "rows_selector": rows_selector,
        "columns": cols,
        "dom_to_api": d2a,
        "api_rows_path": api_rows_path,
        "_data_table_index": idx,
        "_matched": len(d2a),
        "_columns_total": len(cols),
    }
