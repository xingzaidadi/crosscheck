"""
通用计算不变量(optimization 2):断言"落库某字段 == 提交字段的公式"。
金额重算(amount = quantity*unitPrice)、派生值这类服务端计算,做成声明式通用检查,
而非每条用例写死。公式只允许字段名 + 四则运算,安全求值(不是 eval 整串)。

compute 规则(assertions.roundtrip.compute):
  [{field: 落库字段, expr: "quantity * unitPrice", scope: item|header}]
scope=item 时对 item_key 列表逐项算;header 时对顶层算。数字宽松比。
"""
from __future__ import annotations

import ast
import operator

from core.roundtrip import _eq, _num

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.USub: operator.neg}


def _ev(node, vals):
    if isinstance(node, ast.Expression):
        return _ev(node.body, vals)
    if isinstance(node, ast.Constant):      # 数字字面量
        return float(node.value)
    if isinstance(node, ast.Name):          # 字段名 → 取提交值(数字)
        n = _num(vals.get(node.id))
        if n is None:
            raise ValueError(f"字段 {node.id} 非数字:{vals.get(node.id)!r}")
        return n
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_ev(node.left, vals), _ev(node.right, vals))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_ev(node.operand, vals))
    raise ValueError("公式只允许字段名与 + - * / ")


def evaluate(expr: str, vals: dict) -> float:
    return _ev(ast.parse(expr, mode="eval"), vals)


def check_compute(submitted: dict, persisted: dict, rules: list, item_key: str = "") -> tuple[bool, dict]:
    """逐条算"公式(用提交值)== 落库值"。返回 (ok, 报告层)。"""
    cols, rows, ok_all = ["字段", "公式", "算得", "落库值", "一致"], [], True
    persisted = persisted or {}
    for r in rules or []:
        field, expr, scope = r.get("field"), r.get("expr", ""), r.get("scope", "header")
        pairs = []
        if scope == "item" and item_key:
            s_items = submitted.get(item_key) or []
            p_items = persisted.get(item_key) or []
            for i, si in enumerate(s_items):
                pi = p_items[i] if i < len(p_items) else {}
                pairs.append((f"{item_key}[{i}].{field}", si, pi))
        else:
            pairs.append((field, submitted, persisted))
        for label, sv, pv in pairs:
            try:
                expect = evaluate(expr, sv)
            except Exception as e:  # noqa: BLE001
                ok_all = False
                rows.append([label, expr, f"算错:{e}", pv.get(field, "∅"), "✗"])
                continue
            actual = pv.get(field, "∅")
            ok = _eq(expect, actual)
            ok_all = ok_all and ok
            rows.append([label, expr, expect, actual, "✓" if ok else "✗"])
    return ok_all, {"name": "计算不变量(服务端重算)", "ok": ok_all,
                    "expected": "落库字段 == 提交字段公式计算值", "cols": cols, "rows": rows}
