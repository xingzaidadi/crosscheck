"""
哨兵快照 + DB Diff 安全网。

执行安全网(每次):对整库表拍前后行数快照,
  - 发生行数变化的表 ⊆ allowed_tables ?  否则 FAIL(动了未声明的表,潜在缺陷/副作用)。
  - allowed_tables 内的变化视为本次造数(marker 隔离 + 事后清理兜底)。

前提:测试库在本次用例期间安静 → 初期强制串行执行。
大库可只盯 allowed_tables ∪ expected 表(watch 模式),避免全库扫描过慢。
"""
from __future__ import annotations

from core.interfaces import Expected, Verdict
from db.client import DbClient


class SnapshotGuard:
    def __init__(self, db: DbClient, full_scan: bool = True):
        self.db = db
        self.full_scan = full_scan      # True=整库;False=只盯 allowed ∪ expected 表
        self._before: dict[str, int] = {}

    def _watch_tables(self, expected: Expected) -> list[str]:
        if self.full_scan:
            return self.db.tables()
        tabs = set(expected.allowed_tables) | {a.table for a in expected.db}
        return sorted(tabs)

    def _counts(self, tables: list[str]) -> dict[str, int]:
        out = {}
        for t in tables:
            try:
                out[t] = self.db.row_count(t)
            except Exception:  # noqa: BLE001  某些系统表/视图取不到行数,跳过
                pass
        return out

    def snapshot_before(self, expected: Expected) -> None:
        self._before = self._counts(self._watch_tables(expected))

    def snapshot_after(self, expected: Expected, marker: str) -> tuple[Verdict, list[str]]:
        after = self._counts(self._watch_tables(expected))
        allowed = set(expected.allowed_tables)

        changed = [t for t in after
                   if after.get(t) != self._before.get(t, after.get(t))]
        # 新出现/消失的表也算变化
        changed += [t for t in self._before if t not in after]

        unexpected = [t for t in changed if t not in allowed]
        if unexpected:
            deltas = ", ".join(
                f"{t}:{self._before.get(t,'∅')}→{after.get(t,'∅')}" for t in unexpected)
            return Verdict.FAIL, [f"diff 安全网:动了未声明的表 [{deltas}](allowed={sorted(allowed)})"]
        return Verdict.PASS, []

    def model_discovery_diff(self) -> dict:
        """建模阶段:整库表清单前后对比,产出'功能→表'草稿。"""
        after = self._counts(self.db.tables())
        return {t: {"before": self._before.get(t), "after": after.get(t)}
                for t in after if after.get(t) != self._before.get(t)}
