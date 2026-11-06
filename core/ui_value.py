"""
页面数值断言(通用):验页面某处显示的"计算值"(状态页签计数、按钮合计、汇总金额…)
是否 == 库里真值(db_scalar)或字面量(equals)。页签计算/按钮计算这类前端算出的数,
只能读页面 + 对库比。配合 ui 读页面文本用。

value_asserts(spec.ui.value_asserts):
  [{selector: CSS选择器, db_scalar?: "SELECT COUNT(*) ...(返回单值)", equals?: 字面量, label?: 可读名}]
"""
from __future__ import annotations

import re


def _num(s: str) -> str:
    """从文本里抽第一个数字(页签常是 '待处理(12)' 这种);抽不到返回原文去空白。"""
    m = re.search(r"-?\d+(?:\.\d+)?", s or "")
    return m.group(0) if m else (s or "").strip()


def check_values(value_reads: dict, asserts: list[dict], db=None) -> tuple[bool, dict]:
    """逐条比"页面值 vs 库标量/字面量",返回 (ok, 报告层)。"""
    cols = ["页面处", "页面值", "预期", "来源", "一致"]
    rows, ok_all = [], True
    for a in asserts:
        sel = a.get("selector", "")
        name = a.get("label") or sel
        page_raw = value_reads.get(sel, "")
        page_val = _num(page_raw)
        if "db_scalar" in a:
            src = "库"
            if db is None:
                exp, ok = "(无库连接)", False
            else:
                try:
                    r = db.query(a["db_scalar"])
                    exp = str(list(r[0].values())[0]) if r else ""
                except Exception as e:  # noqa: BLE001
                    exp = f"查询失败:{e}"
        else:
            exp, src = str(a.get("equals", "")), "字面量"
        ok = (page_val != "" and (page_val == _num(exp) or page_raw.strip() == exp))
        ok_all = ok_all and ok
        rows.append([name, page_raw, exp, src, "✓" if ok else "✗"])
    return ok_all, {"name": "页面数值校验(页签/按钮计算)", "ok": ok_all,
                    "expected": "页面显示的计算值 == 库真值/预期", "cols": cols, "rows": rows}
