"""
对抗/边界用例生成(optimization 3):从库约束(db_intel.table_constraints)自动派生"非法输入",
预期被拒。负向/边界用例不用人写;顺带能抓出"后端没按约束校验"的 bug(如约束在库却不拦)。

从约束派生的非法值(business-agnostic):
  required(NOT NULL 无默认非自增)→ 留空
  enum                          → 给一个不在枚举里的值
  数字类型(int/decimal/…)      → 给非数字
每条带 why(为什么非法),供报告/判读。列名是库列(snake),运行器据此映射回提交体字段。
"""
from __future__ import annotations

_NUMERIC = ("int", "decimal", "numeric", "float", "double", "bigint", "tinyint", "smallint")


def gen_invalid(constraints: dict) -> list[dict]:
    """约束字典 → 非法输入列表 [{column, value, why, kind}]。"""
    out = []
    for col, c in (constraints or {}).items():
        if c.get("auto"):
            continue
        if c.get("required"):
            out.append({"column": col, "value": "", "why": "必填字段留空应被拒", "kind": "required"})
        enum = c.get("enum") or []
        if enum:
            out.append({"column": col, "value": "__NOT_IN_ENUM__",
                        "why": f"非法枚举值应被拒(合法:{enum[:4]})", "kind": "enum"})
        t = (c.get("type") or "").lower()
        if any(x in t for x in _NUMERIC):
            out.append({"column": col, "value": "abc",
                        "why": "数字字段给非数字应被拒", "kind": "type"})
    return out
