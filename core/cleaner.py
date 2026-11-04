"""
清理 + 登记册:数据隔离三件套之一,外加"清理失败兜底"。

- 登记册持久化:每条造数登记 {marker, 表, 状态},清理成功才销账。
- 失败也清;清理失败(超时/外键/权限)标 cleanup_pending,不中断后续用例。
- 每次执行前先 retry_pending() 扫残留重试;清不掉的集中告警。
- 哨兵快照需排除 cleanup_pending 的已知标记值,避免误报脏库。
"""
from __future__ import annotations

import json
from pathlib import Path

from core.interfaces import TestCase
from db.client import DbClient


class Cleaner:
    def __init__(self, db: DbClient, registry_path: str | Path = ".cleanup_registry.json"):
        self.db = db
        self.registry_path = Path(registry_path)

    def register(self, case: TestCase, marker: str) -> None:
        """执行前登记:本次将在哪些表按 marker 造数。"""
        # TODO: 把 {marker, feature, 涉及表, status=pending} 落盘到登记册
        ...

    def cleanup(self, marker: str) -> bool:
        """按 marker 反删本次造数。成功销账,失败标 cleanup_pending。返回是否清干净。"""
        # TODO: 对登记的每张表 DELETE ... WHERE <标记列> LIKE marker
        # TODO: 失败不抛,标 pending,返回 False
        return True

    def retry_pending(self) -> list[str]:
        """执行前扫描上次没清掉的残留并重试;返回仍清不掉的 marker 列表(供告警 + diff 排除)。"""
        # TODO
        return []

    def known_markers(self) -> list[str]:
        """返回当前所有 pending 残留 marker,给 SnapshotGuard 排除,避免误报脏库。"""
        # TODO
        return []
