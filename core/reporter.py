"""报告:汇总每条用例的判定,输出人能读、机器也能解析的结果。"""
from __future__ import annotations

from .interfaces import CaseResult, Verdict


class Reporter:
    def __init__(self):
        self.results: list[CaseResult] = []

    def add(self, result: CaseResult) -> None:
        self.results.append(result)

    def summary(self) -> dict:
        by = {v: 0 for v in Verdict}
        for r in self.results:
            by[r.verdict] += 1
        return {
            "total": len(self.results),
            "pass": by[Verdict.PASS],
            "fail": by[Verdict.FAIL],
            "env_error": by[Verdict.ENV_ERROR],
            "aborted": by[Verdict.ABORTED],
            "cleanup_failed": sum(1 for r in self.results if not r.cleanup_ok),
        }

    def render(self) -> str:
        """骨架:先打印文本;日后可出 HTML / JSON。"""
        lines = ["=== 测试报告 ==="]
        for r in self.results:
            lines.append(f"[{r.verdict.value.upper():9}] {r.case_id}  ({r.duration_s}s)")
            for d in r.details:
                lines.append(f"    - {d}")
            if not r.cleanup_ok:
                lines.append("    ! 清理未完成(已标 cleanup_pending)")
        lines.append(f"\n小结: {self.summary()}")
        return "\n".join(lines)
