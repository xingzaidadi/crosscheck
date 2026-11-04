"""
哨兵快照 + DB Diff 安全网。

两个用途(实施方案第 7 节):
  1. 建模引导(低频):整库表清单前后对比,自动测出"功能→表",能发现新建表。
  2. 执行安全网(每次):实际动的表须 ⊆ allowed_tables;标记值之外出现变化 → 本次作废。

前提:测试库在本次用例期间安静 → 初期强制串行执行。
"""
from __future__ import annotations

from core.interfaces import Expected, Verdict
from db.client import DbClient


class SnapshotGuard:
    def __init__(self, db: DbClient):
        self.db = db
        self._before: dict[str, dict] = {}   # table -> {max_id, count}

    def snapshot_before(self, expected: Expected) -> None:
        """对相关表拍前置快照:表清单 + max(id) + count。"""
        # TODO: 对 expected.db 涉及的表 + allowed_tables 取 max(pk) 和 count(*)
        self._before = {}

    def snapshot_after(self, expected: Expected, marker: str) -> tuple[Verdict, list[str]]:
        """
        后置快照并比对:
          - 变化表 ⊆ allowed_tables ?  否则 FAIL(潜在缺陷)
          - 除 marker 造数外有无意外变化 ?  有则 ABORTED(疑似脏库,作废重跑)
        """
        # TODO: 取后置快照,算 diff;按 marker 过滤本次造数;已知 cleanup_pending 残留也要排除
        changed_tables: list[str] = []
        allowed = set(expected.allowed_tables)

        unexpected = [t for t in changed_tables if t not in allowed]
        if unexpected:
            return Verdict.FAIL, [f"diff 安全网:动了未声明的表 {unexpected}"]

        # TODO: 检测标记外变化 → Verdict.ABORTED
        return Verdict.PASS, []

    def model_discovery_diff(self) -> dict:
        """建模阶段:整库表清单前后对比,产出'功能→表'草稿喂给生成器/知识库。"""
        # TODO
        return {}
