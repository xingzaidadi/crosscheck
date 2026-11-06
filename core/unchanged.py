"""
副作用防护(optimization 5):守卫/负向用例要"数据不变"。操作前拍一张记录字段快照,
操作后再拍,比对——任何**不该变却变了的字段**现形(比断言固定值更强:连你没预测到的
意外改动也抓)。被拒的操作若偷偷改了数据,就是这类能抓的 bug。

unchanged 配置(assertions.unchanged):
  {table, where(marker/{{var}} 模板), fields?:[列...]}  —— fields 省略=比该行所有列
"""
from __future__ import annotations


def render_where(where: str, marker: str, vars: dict | None = None) -> str:
    w = (where or "").replace("{{AUTOTEST_标记值}}", marker)
    for k, v in (vars or {}).items():
        w = w.replace("{{" + k + "}}", str(v))
    return w


def read_fields(db, table: str, where: str, fields=None) -> dict | None:
    """取匹配行的字段快照(第一行)。无行返回 None。"""
    rows = db.query(f"SELECT * FROM {table} WHERE {where} LIMIT 1")
    if not rows:
        return None
    r = rows[0]
    return {k: r.get(k) for k in fields} if fields else dict(r)


def diff(before: dict | None, after: dict | None, fields=None) -> tuple[bool, dict]:
    """比前后快照,返回 (不变=ok, 报告层)。行消失/新增也算变。"""
    cols = ["字段", "操作前", "操作后", "一致"]
    if before is None or after is None:
        return False, {"name": "副作用防护(数据不变)", "ok": False,
                       "note": f"记录前后存在性变化(前{'有' if before else '无'}→后{'有' if after else '无'})",
                       "cols": cols, "rows": []}
    keys = fields or list(before.keys())
    rows, changed = [], []
    for k in keys:
        b, a = before.get(k), after.get(k)
        same = str(b) == str(a)
        if not same:
            changed.append(k)
            rows.append([k, b, a, "✗"])
    ok = not changed
    if ok:
        rows = [["(所列字段均未变)", "", "", "✓"]]
    return ok, {"name": "副作用防护(数据不变)", "ok": ok,
                "expected": "被拒/守卫操作后,目标记录字段不被改动",
                "actual": "未变" if ok else f"{len(changed)} 个字段被改:{changed}",
                "cols": cols, "rows": rows}
