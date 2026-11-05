"""
校验:API 响应断言 + DB 精确断言 + 页面预期(diff 安全网在 SnapshotGuard 里)。

失败必须给"预期X vs 实际Y,差在哪字段",不能只说"校验失败"。
用例里的 {{AUTOTEST_标记值}} 占位在查询/断言前统一替换成本次 marker。
"""
from __future__ import annotations

from typing import Any

from core.interfaces import ActionResult, TestCase, Verdict
from db.client import DbClient

_MARKER_PH = "{{AUTOTEST_标记值}}"


def _dig(obj: Any, path: str) -> Any:
    """按点路径取值:data.total / data.list.0.id。取不到返回 _MISSING。"""
    cur = obj
    for seg in path.split("."):
        if isinstance(cur, dict):
            if seg not in cur:
                return _MISSING
            cur = cur[seg]
        elif isinstance(cur, (list, tuple)):
            try:
                cur = cur[int(seg)]
            except (ValueError, IndexError):
                return _MISSING
        else:
            return _MISSING
    return cur


_MISSING = object()


def _eq(a: Any, b: Any) -> bool:
    if a == b:
        return True
    return str(a) == str(b)   # DB 返回 int、用例写 str 时也算相等


class Verifier:
    def __init__(self, db: DbClient):
        self.db = db

    def verify(self, case: TestCase, marker: str, action: ActionResult) -> tuple[Verdict, list[str]]:
        details: list[str] = []
        resp_ok, d = self._verify_response(case, action)
        details += d
        page_ok, d = self._verify_page(case, action)
        details += d
        db_ok, d = self._verify_db(case, marker)
        details += d
        verdict = Verdict.PASS if (resp_ok and page_ok and db_ok) else Verdict.FAIL
        if verdict is Verdict.PASS and not details:
            details = ["响应 + 库断言全部通过"]
        return verdict, details

    def _verify_response(self, case: TestCase, action: ActionResult) -> tuple[bool, list[str]]:
        ra = (case.raw or {}).get("response_assert") or {}
        if not ra:
            return True, []
        ok, details = True, []
        if not action.ok and action.error:
            ok = False
            details.append(f"响应错误: {action.error}")
        if "status" in ra and action.api_status != ra["status"]:
            ok = False
            details.append(f"响应状态: 预期 {ra['status']} vs 实际 {action.api_status}")
        for path, expected in (ra.get("body") or {}).items():
            actual = _dig(action.api_body, path)
            if actual is _MISSING:
                ok = False
                details.append(f"响应字段缺失: {path}")
            elif not _eq(actual, expected):
                ok = False
                details.append(f"响应字段 {path}: 预期 {expected!r} vs 实际 {actual!r}")
        return ok, details

    def _verify_page(self, case: TestCase, action: ActionResult) -> tuple[bool, list[str]]:
        want = case.expected.page or []
        if not want:
            return True, []
        texts = " ".join(action.page_texts or [])
        missing = [w for w in want if w not in texts]
        if missing:
            return False, [f"页面预期未命中: {missing}"]
        return True, []

    def _verify_db(self, case: TestCase, marker: str) -> tuple[bool, list[str]]:
        ok, details = True, []
        for a in case.expected.db:
            where = a.where.replace(_MARKER_PH, marker)
            try:
                rows = self.db.query(f"SELECT * FROM {a.table} WHERE {where}")
            except Exception as e:  # noqa: BLE001
                ok = False
                details.append(f"[{a.table}] 查询失败: {e}")
                continue
            if a.row_count is not None and len(rows) != a.row_count:
                ok = False
                details.append(f"[{a.table}] 行数: 预期 {a.row_count} vs 实际 {len(rows)} (where: {where})")
            for col, expected in (a.fields or {}).items():
                bad = [r for r in rows if not _eq(r.get(col), expected)]
                if bad:
                    got = bad[0].get(col)
                    ok = False
                    details.append(f"[{a.table}] 字段 {col}: 预期 {expected!r} vs 实际 {got!r}")
        return ok, details
