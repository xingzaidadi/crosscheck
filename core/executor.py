"""
执行器 —— 一条用例的生命周期编排。控制流写死,不让 AI 驱动。

对应实施方案第 5 节的 10 步工作流。AI 只在选择器失效自愈时被适配器内部调用。
"""
from __future__ import annotations

import time

from .interfaces import Adapter, CaseResult, TestCase, Verdict
from .knowledge import KnowledgeBase
from .marker import make_marker
from .snapshot import SnapshotGuard
from .verifier import Verifier
from .cleaner import Cleaner
from .reporter import Reporter


class Executor:
    def __init__(
        self,
        kb: KnowledgeBase,
        adapter: Adapter,
        guard: SnapshotGuard,
        verifier: Verifier,
        cleaner: Cleaner,
        reporter: Reporter,
    ):
        self.kb = kb
        self.adapter = adapter
        self.guard = guard
        self.verifier = verifier
        self.cleaner = cleaner
        self.reporter = reporter

    def run_case(self, case: TestCase) -> CaseResult:
        t0 = time.time()
        marker = make_marker(case.case_id)

        # 执行前:先扫上次没清掉的残留(清理失败兜底)
        # TODO: self.cleaner.retry_pending()

        self.cleaner.register(case, marker)       # 登记将造数据

        try:
            # 3. 前置哨兵快照(相关表清单 + max(id) + count)
            self.guard.snapshot_before(case.expected)

            # 1+4. 读知识库 + 按页面模型回放步骤(选择器失效才 AI 自愈)
            self.adapter.setup(case)
            action = self.adapter.perform(case, marker)

            # 6. 三重校验
            verdict, details = self.verifier.verify(case, marker, action)

            # 6c. diff 安全网:实际动的表须 ⊆ allowed_tables,标记外无意外变化
            diff_verdict, diff_details = self.guard.snapshot_after(case.expected, marker)
            if diff_verdict is Verdict.ABORTED:
                verdict, details = Verdict.ABORTED, diff_details
            elif diff_verdict is Verdict.FAIL and verdict is Verdict.PASS:
                verdict, details = Verdict.FAIL, diff_details

        except Exception as e:  # noqa: BLE001  骨架:先兜住,细分留 TODO
            verdict, details = Verdict.ENV_ERROR, [f"执行异常: {e}"]

        finally:
            self.adapter.teardown()

        # 8. 清理(失败也清);清不掉标记 pending,不中断
        cleanup_ok = self.cleaner.cleanup(marker)

        # 9. 回写知识库(新发现映射/规则,标记待审) —— TODO
        # self.kb.write_back_pending(...)

        result = CaseResult(
            case_id=case.case_id,
            verdict=verdict,
            details=details,
            cleanup_ok=cleanup_ok,
            duration_s=round(time.time() - t0, 2),
        )
        self.reporter.add(result)
        return result
