"""
清理 + 登记册:数据隔离三件套之一,外加"清理失败兜底"。

- 登记册持久化:每条造数登记 {marker, 表+标记列, 状态},清理成功才销账。
- 失败也清;清理失败(超时/外键/权限)标 cleanup_pending,不中断后续用例。
- 每次执行前先 retry_pending() 扫残留重试;清不掉的集中告警。
- 哨兵快照需排除 cleanup_pending 的已知标记值,避免误报脏库。

清理目标从用例的 raw["cleanup_targets"] 来:[{table, column}],子表在前、主表在后(避外键)。
按 marker 反删:DELETE FROM <table> WHERE <column> LIKE '%<marker>%'。
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

    def _load(self) -> dict:
        if self.registry_path.exists():
            try:
                return json.loads(self.registry_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                return {}
        return {}

    def _save(self, reg: dict) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(
            json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")

    def register(self, case: TestCase, marker: str) -> None:
        """执行前登记:本次将在哪些表按 marker 造数(status=pending)。"""
        targets = (case.raw or {}).get("cleanup_targets") or []
        reg = self._load()
        reg[marker] = {"feature": case.feature, "targets": targets, "status": "pending"}
        self._save(reg)

    def cleanup(self, marker: str) -> bool:
        """按 marker 反删本次造数。全清成功则销账;失败标 cleanup_pending,返回 False。"""
        reg = self._load()
        entry = reg.get(marker)
        if not entry:
            return True
        ok, errors = True, []
        # 子表在前、主表在后(避外键)。两种目标:
        #   直接:{table, column}            —— DELETE WHERE column LIKE %marker%
        #   父查:{table, key, parent:{table, key_col, marker_col}}
        #        —— DELETE WHERE key IN (SELECT key_col FROM parent WHERE marker_col LIKE %marker%)
        for t in entry.get("targets", []):
            table = t.get("table")
            if not table:
                continue
            try:
                parent = t.get("parent")
                if parent:
                    sql = (f"DELETE FROM {table} WHERE {t['key']} IN "
                           f"(SELECT {parent['key_col']} FROM {parent['table']} "
                           f"WHERE {parent['marker_col']} LIKE :m)")
                    self.db.execute_write(sql, {"m": f"%{marker}%"})
                elif t.get("column"):
                    self.db.execute_write(
                        f"DELETE FROM {table} WHERE {t['column']} LIKE :m", {"m": f"%{marker}%"})
            except Exception as e:  # noqa: BLE001  清理失败不抛,标 pending
                ok = False
                errors.append(f"{table}: {e}")
        if ok:
            reg.pop(marker, None)
        else:
            entry["status"] = "cleanup_pending"
            entry["errors"] = errors
            reg[marker] = entry
        self._save(reg)
        return ok

    def retry_pending(self) -> list[str]:
        """执行前扫上次残留重试;返回仍清不掉的 marker(供告警 + diff 排除)。"""
        still = []
        for marker in list(self._load().keys()):
            if not self.cleanup(marker):
                still.append(marker)
        return still

    def known_markers(self) -> list[str]:
        """当前所有残留 marker,给 SnapshotGuard 排除,避免误报脏库。"""
        return list(self._load().keys())
