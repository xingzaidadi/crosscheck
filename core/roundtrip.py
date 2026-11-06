"""
全字段对账(round-trip,通用):写入后把"提交了什么"与"详情接口返回的持久化记录"逐字段比。
只验一两列会漏 bug;这里比提交体里每个标量字段(+ 子项列表),服务端漏填/改写/截断立刻现形。

- 数字宽松比:"2" 与 "2.0000" 视为相等(避开小数格式噪音),抓的是真差异;
- ignore:服务端合法生成/改写的字段(id/单号/状态/版本/时间/金额重算…)跳过;
- 嵌套 dict 跳过(只比标量),子项列表按 item_key 逐项逐字段比。
"""
from __future__ import annotations


def _num(x):
    try:
        return float(str(x).strip())
    except (ValueError, TypeError):
        return None


def _eq(a, b) -> bool:
    if str(a) == str(b):
        return True
    na, nb = _num(a), _num(b)
    return na is not None and nb is not None and na == nb


def compare(submitted: dict, persisted: dict, *, ignore=(), item_key: str = "",
            item_ignore=()) -> tuple[bool, list, dict]:
    """逐字段比提交体 vs 持久化记录。返回 (ok, 差异列表[(字段,提交值,落库值)], 报告层)。"""
    ig, iig = set(ignore), set(item_ignore)
    mism = []
    persisted = persisted or {}

    def scalar_items(d):
        return {k: v for k, v in (d or {}).items() if not isinstance(v, (dict, list))}

    for k, v in scalar_items(submitted).items():
        if k in ig:
            continue
        pv = persisted.get(k, "∅")
        if not _eq(v, pv):
            mism.append((k, v, pv))

    if item_key:
        s_items = submitted.get(item_key) or []
        p_items = persisted.get(item_key) or []
        for i, si in enumerate(s_items):
            pi = p_items[i] if i < len(p_items) else {}
            for k, v in scalar_items(si).items():
                if k in iig:
                    continue
                pv = (pi or {}).get(k, "∅")
                if not _eq(v, pv):
                    mism.append((f"{item_key}[{i}].{k}", v, pv))

    ok = not mism
    cols = ["字段", "提交值", "落库值"]
    rows = [[k, sv, pv] for k, sv, pv in mism] or [["(全部字段一致)", "", ""]]
    return ok, mism, {"name": "全字段对账(提交 ↔ 落库)", "ok": ok,
                      "expected": "提交的每个字段都如实持久化(服务端生成/重算字段除外)",
                      "actual": "一致" if ok else f"{len(mism)} 个字段不一致",
                      "cols": cols, "rows": rows}
