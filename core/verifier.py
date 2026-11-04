"""
三重校验:页面预期 + DB 精确断言 +(diff 安全网在 SnapshotGuard 里)。

失败必须给"预期X vs 实际Y,差在哪字段",不能只说"校验失败"。
"""
from __future__ import annotations

from core.interfaces import ActionResult, TestCase, Verdict
from db.client import DbClient


class Verifier:
    def __init__(self, db: DbClient):
        self.db = db

    def verify(
        self, case: TestCase, marker: str, action: ActionResult
    ) -> tuple[Verdict, list[str]]:
        details: list[str] = []

        # a. 页面预期:看提示/卡片/文案(用 success_indicator 定位,非 AI 猜)
        page_ok, page_detail = self._verify_page(case, action)
        details += page_detail

        # b. DB 预期:按用例 where + assert 查库比对(marker 代入占位符)
        db_ok, db_detail = self._verify_db(case, marker)
        details += db_detail

        verdict = Verdict.PASS if (page_ok and db_ok) else Verdict.FAIL
        return verdict, details

    def _verify_page(self, case: TestCase, action: ActionResult) -> tuple[bool, list[str]]:
        # TODO: 比对 action.page_texts / success_indicator 命中与否
        return True, []

    def _verify_db(self, case: TestCase, marker: str) -> tuple[bool, list[str]]:
        ok = True
        details: list[str] = []
        for a in case.expected.db:
            where = a.where.replace("{{AUTOTEST_标记值}}", marker)
            # TODO: rows = self.db.query(a.db, a.table, where)
            # TODO: 校验 row_count;逐字段比对 a.fields,记录"预期X vs 实际Y @字段"
            _ = where
        return ok, details
