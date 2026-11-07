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


_DUMP_JS = """()=>Array.from(document.querySelectorAll('table')).map(t=>{
  const wrap=t.closest('[class*=table]');
  return {
    wrapper:(wrap?wrap.className:''),
    headers:Array.from(t.querySelectorAll('thead th')).map(x=>x.innerText.trim()),
    row0:Array.from(t.querySelectorAll('tbody tr:first-child td')).map(x=>x.innerText.trim()),
    rows:t.querySelectorAll('tbody tr').length
  };
})"""


def probe_page_extract(page_url: str, *, session_file: str | None = None,
                       api_pattern: str = "", actions: list | None = None,
                       api_rows_path: str = "data.records", wait_ms: int = 3500,
                       headless: bool = True) -> dict:
    """实开页面:做触发动作 → 抓接口响应 → dump 所有表结构 → build_extract。
    actions: [{click:{selector}}|{goto:url}|{wait_ms:ms}] 轻量触发序列。
    返回 {extract, api_rows, tables, api_total}。零业务:哪个页面/接口由调用方给。"""
    from playwright.sync_api import sync_playwright

    cap = {"rows": None, "total": None}

    def _rows_from(d):
        node = d
        for part in api_rows_path.split("."):
            node = node.get(part) if isinstance(node, dict) else None
            if node is None:
                break
        if isinstance(node, list):
            return node
        data = d.get("data") if isinstance(d, dict) else None
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list):
                    return v
        return []

    with sync_playwright() as p:
        b = p.chromium.launch(headless=headless)
        kw = {"viewport": {"width": 1600, "height": 900}}
        if session_file:
            kw["storage_state"] = session_file
        ctx = b.new_context(**kw)
        pg = ctx.new_page()

        def on_resp(resp):
            if api_pattern and api_pattern in resp.url and cap["rows"] is None:
                try:
                    d = resp.json()
                    cap["rows"] = _rows_from(d)
                    data = d.get("data") if isinstance(d, dict) else {}
                    cap["total"] = data.get("total") if isinstance(data, dict) else None
                except Exception:  # noqa: BLE001
                    pass
        ctx.on("response", on_resp)

        pg.goto(page_url, wait_until="networkidle", timeout=30000)
        pg.wait_for_timeout(wait_ms)
        for a in (actions or []):
            try:
                if "click" in a:
                    pg.locator(a["click"]["selector"]).first.click(timeout=4000)
                elif "goto" in a:
                    pg.goto(a["goto"], wait_until="networkidle", timeout=20000)
                elif "wait_ms" in a:
                    pg.wait_for_timeout(int(a["wait_ms"]))
                pg.wait_for_timeout(1500)
            except Exception:  # noqa: BLE001
                pass
        pg.wait_for_timeout(1200)
        tables = pg.evaluate(_DUMP_JS)
        ctx.close()
        b.close()

    extract = build_extract(tables, cap["rows"] or [], api_rows_path=api_rows_path)
    return {"extract": extract, "api_rows": cap["rows"] or [], "tables": tables, "api_total": cap["total"]}


_DETAIL_JS = """()=>{
  // 通用找"标签-值"对:描述列表/表单项,标签子节点含 label、值子节点含 content/value
  const groups=['[class*=descriptions-item]','[class*=descriptions__item]','[class*=form-item]','[class*=detail-item]','[class*=desc-item]'];
  let best={pairs:[],label_sel:'',content_sel:'',n:0};
  for(const g of groups){
    const items=document.querySelectorAll(g); if(!items.length) continue;
    const pairs=[]; let lsel='',csel='';
    items.forEach(it=>{
      const lab=it.querySelector('[class*=label]');
      const val=it.querySelector('[class*=content],[class*=value]');
      if(lab&&val){ pairs.push({label:lab.innerText.trim(), value:val.innerText.trim()});
        if(!lsel){ lsel=g+' [class*=label]'; csel=g+' [class*=content],'+g+' [class*=value]'; } }
    });
    if(pairs.length>best.n) best={pairs,label_sel:lsel,content_sel:csel,n:pairs.length};
  }
  return best;
}"""


def build_detail_extract(pairs: list[dict], api_obj: dict, *, label_sel: str, content_sel: str,
                         api_rows_path: str = "data") -> dict:
    """详情面板:标签-值对 + 接口单对象 → ui.extract(fields 模式)+ dom_to_api(按值绑定)。"""
    api_norm = {k: _norm(v) for k, v in (api_obj or {}).items() if not isinstance(v, (dict, list))}
    d2a, used = {}, set()
    for p in pairs:
        lab = (p.get("label") or "").strip()
        dv = _norm(p.get("value"))
        if not lab or dv in ("", "-", "—"):
            continue
        slug = re.sub(r"\s+", "", lab)
        for k, v in api_norm.items():
            if v != "" and v == dv and k not in used:
                d2a[slug] = k
                used.add(k)
                break
    return {
        "extract": {"fields": {"label": label_sel, "value": content_sel}},
        "dom_to_api": d2a,
        "api_rows_path": api_rows_path,
        "_matched": len(d2a),
        "_pairs": len(pairs),
    }


def probe_detail_fields(page_url: str, *, session_file: str | None = None,
                        api_pattern: str = "", actions: list | None = None,
                        api_rows_path: str = "data", wait_ms: int = 3500,
                        headless: bool = True) -> dict:
    """实探详情页:触发(点进详情)→抓详情接口(data 为单对象)→dump 标签-值对→build_detail_extract。"""
    from playwright.sync_api import sync_playwright
    cap = {"obj": None}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=headless)
        kw = {"viewport": {"width": 1600, "height": 900}}
        if session_file:
            kw["storage_state"] = session_file
        ctx = b.new_context(**kw); pg = ctx.new_page()

        def on_resp(resp):
            if api_pattern and api_pattern in resp.url and cap["obj"] is None:
                try:
                    d = resp.json(); cap["obj"] = d.get("data") if isinstance(d, dict) else None
                except Exception:  # noqa: BLE001
                    pass
        ctx.on("response", on_resp)
        pg.goto(page_url, wait_until="networkidle", timeout=30000); pg.wait_for_timeout(wait_ms)
        for a in (actions or []):
            try:
                if "click" in a:
                    pg.locator(a["click"]["selector"]).first.click(timeout=4000)
                elif "wait_ms" in a:
                    pg.wait_for_timeout(int(a["wait_ms"]))
                pg.wait_for_timeout(1500)
            except Exception:  # noqa: BLE001
                pass
        pg.wait_for_timeout(1200)
        det = pg.evaluate(_DETAIL_JS)
        ctx.close(); b.close()
    obj = cap["obj"] if isinstance(cap["obj"], dict) else {}
    ex = build_detail_extract(det.get("pairs", []), obj, label_sel=det.get("label_sel", ""),
                              content_sel=det.get("content_sel", ""), api_rows_path=api_rows_path)
    return {"extract": ex, "api_obj": obj, "pairs": det.get("pairs", [])}


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
