"""异步事件口径自发现(通用、零业务):很多写动作的下游效果是**异步**落地的(事件消费→事件表、
异步导出、通知、MQ)。手工测它要"等多久、断哪张表"——eventmap 自动学:
触发一次写 → 轮询一批表的行数 → 记录哪些表"涨了"(事件落地)、各自多久才涨 → 推出等待口径。

纯计数差分,不认识任何业务:看的是"触发后哪些表新增了行",表清单由调用方(schema/发现)给。
产出可直接喂 engine 的 verify_poll/event_asserts(timeout/interval + 涨了的表)。

可测纯函数:learn_events(注入 count_fn/sleep/clock)/ suggest_poll
活编排:build_eventmap
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Callable


def learn_events(tables: list[str], trigger_fn: Callable[[], Any], *,
                 settle_s: float = 30.0, interval_s: float = 2.0, quiet_rounds: int = 2,
                 count_fn: Callable[[str], int],
                 sleep_fn: Callable[[float], Any] = time.sleep,
                 clock: Callable[[], float] = time.monotonic) -> dict:
    """触发 trigger_fn 前拍各表行数,触发后每 interval_s 轮询;某表行数首次增加即记"fired + 首次出现秒数"。
    连续 quiet_rounds 轮无新增 或 超 settle_s 停。返回 {table:{fired,delta,first_seen_s}} + settled_s。"""
    before = {t: count_fn(t) for t in tables}
    result = {t: {"fired": False, "delta": 0, "first_seen_s": None} for t in tables}

    trigger_fn()
    t0 = clock()
    quiet = 0
    while True:
        sleep_fn(interval_s)
        elapsed = round(clock() - t0, 2)
        grew = False
        for t in tables:
            cur = count_fn(t)
            d = cur - before[t]
            if d > 0:
                r = result[t]
                if not r["fired"]:
                    r["fired"] = True
                    r["first_seen_s"] = elapsed
                if d > r["delta"]:
                    r["delta"] = d
                    grew = True
        quiet = 0 if grew else quiet + 1
        if quiet >= quiet_rounds or (clock() - t0) >= settle_s:
            break
    return {"tables": result, "settled_s": round(clock() - t0, 2)}


def suggest_poll(result: dict, *, safety: float = 1.5, min_timeout_s: float = 6.0) -> dict:
    """由学到的首次出现时间推等待口径:timeout = 最慢事件 × 安全系数(下限 min);interval 取学习间隔或 2s。
    并列出"涨了的表"供 event_asserts 用。"""
    fired = {t: v for t, v in result.get("tables", {}).items() if v.get("fired")}
    slowest = max((v["first_seen_s"] or 0) for v in fired.values()) if fired else 0.0
    timeout = max(min_timeout_s, math.ceil(slowest * safety))
    return {"timeout_s": int(timeout), "interval_s": 2,
            "event_tables": sorted(fired.keys()),
            "learned_slowest_s": slowest}


def build_eventmap(site: str, triggers: list[dict], *, db=None,
                   count_fn: Callable[[str], int] | None = None) -> dict:
    """批量学。triggers: [{key, tables, trigger_fn, settle_s?, interval_s?}]。
    count_fn 默认用 db.row_count;各 trigger 独立容错。落 kb/eventmap/<site>.json。"""
    cf = count_fn or (lambda t: db.row_count(t))
    out: dict[str, Any] = {}
    for tr in triggers:
        key = tr.get("key") or ""
        try:
            res = learn_events(tr["tables"], tr["trigger_fn"], count_fn=cf,
                               settle_s=tr.get("settle_s", 30.0), interval_s=tr.get("interval_s", 2.0))
            out[key] = {"ok": True, **suggest_poll(res), "raw": res}
        except Exception as e:  # noqa: BLE001
            out[key] = {"ok": False, "missing": f"学习异常: {str(e)[:100]}"}
    save_eventmap(site, out)
    return out


def save_eventmap(site: str, mp: dict) -> Path:
    from core.workspace import kb_dir
    out = kb_dir() / "eventmap" / f"{site}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(mp, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def load_eventmap(site: str) -> dict:
    from core.workspace import kb_dir
    p = kb_dir() / "eventmap" / f"{site}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
