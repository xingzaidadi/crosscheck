"""
异步/事件校验(通用,两源):等异步动作产生的"事件/通知"落地,再按标记断言。

一条写动作常触发异步链路(事件消费、异步导出、飞书/MQ 通知),不是同步就能验的。
本模块提供**与业务无关**的"等待 + 轮询 + 计数断言"原语,两种事件源可插拔:
  - source=db  : 事件落在库表/outbox 表 —— COUNT(带标记的行)。
  - source=http: 事件暴露为可查接口(通知日志/outbox API/消息查询网关)—— 拉回列表,数带标记的条数。
配置全在 spec.assertions.events(落 workspace),框架只认 source/match/min_count/within_s 这些通用键。

事件断言项(通用键):
  {source: db|http, min_count: 1, within_s: 10, interval_s: 2, name: "可读名",
   # db:   table, where(支持 {{AUTOTEST_标记值}} / {{var}})
   # http: method,url,base_url?,session?,body?, list_path(响应里数组的点路径), match_field(该字段含 marker 即命中)}
"""
from __future__ import annotations

import json
import time

from core.verifier import _dig, _MISSING


def _match_count(items, match_field: str | None, marker: str) -> int:
    """数带标记的条目:给了 match_field 就比该字段,否则整条(序列化后)含 marker 即算命中。"""
    n = 0
    for it in items or []:
        if match_field:
            v = it.get(match_field) if isinstance(it, dict) else None
            hit = v is not None and marker in str(v)
        else:
            hit = marker in json.dumps(it, ensure_ascii=False, default=str)
        if hit:
            n += 1
    return n


def _http_count(cfg: dict, marker: str, vars: dict | None) -> tuple[int, int | None]:
    from adapters.api_adapter import ApiAdapter
    ad = ApiAdapter(base_url=cfg.get("base_url", ""), session_file=cfg.get("session"))
    try:
        ad.setup()
        r = ad.call({"method": cfg.get("method", "GET"), "url": cfg["url"], "body": cfg.get("body")},
                    {**(vars or {}), "marker": marker})
    finally:
        ad.teardown()
    items = _dig(r.api_body, cfg.get("list_path", "data.list"))
    if items is _MISSING:
        items = []
    return _match_count(items, cfg.get("match_field"), marker), r.api_status


def _db_count(db, cfg: dict, marker: str, vars: dict | None) -> int:
    where = cfg["where"].replace("{{AUTOTEST_标记值}}", marker)
    for k, v in (vars or {}).items():
        where = where.replace("{{" + k + "}}", str(v))
    return db.query(f"SELECT COUNT(*) AS c FROM {cfg['table']} WHERE {where}")[0]["c"]


def check_events(asserts: list[dict], *, marker: str, vars: dict | None = None, db=None,
                 base_url: str = "", session_file: str = "", default_within: float = 10
                 ) -> tuple[bool, list[str], list[dict]]:
    """逐条事件断言:在 within_s 内轮询事件源,带标记命中数 ≥ min_count 则通过。返回 (ok, details, layers)。"""
    ok_all, details, layers = True, [], []
    for a in asserts:
        src = a.get("source", "db")
        mn = int(a.get("min_count", 1))
        within = float(a.get("within_s", default_within))
        interval = float(a.get("interval_s", 2))
        deadline = time.time() + within
        got, status, err = 0, None, None
        while True:
            try:
                if src == "http":
                    cfg = dict(a)
                    cfg.setdefault("base_url", base_url)
                    cfg.setdefault("session", session_file)
                    got, status = _http_count(cfg, marker, vars)
                else:
                    got = _db_count(db, a, marker, vars)
                err = None
            except Exception as e:  # noqa: BLE001  源暂不可达,轮询内重试
                err = str(e)
            if (err is None and got >= mn) or time.time() >= deadline:
                break
            time.sleep(interval)
        ok = err is None and got >= mn
        ok_all = ok_all and ok
        name = a.get("name") or (f"事件表 {a.get('table')}" if src == "db" else f"外部通知 {a.get('url')}")
        note = f"源不可达:{err}" if err else ""
        details.append(f"事件断言[{name}]: 需≥{mn} 实际 {got}" + ("" if ok else " ✗"))
        layers.append({"name": f"异步事件校验:{name}", "ok": ok,
                       "expected": f"{within:.0f}s 内产生 ≥{mn} 条带标记的事件/通知(源={src})",
                       "actual": f"命中 {got} 条" + (f" · HTTP {status}" if status is not None else ""),
                       "tables": [a["table"]] if (src == "db" and a.get("table")) else [],
                       "note": note})
    return ok_all, details, layers
