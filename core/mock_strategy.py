"""Local strategy capability pack for the G4 requirement-to-strategy slice."""
from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from .business_capabilities import CapabilityPack


class MockStrategyStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS strategies (
          id TEXT PRIMARY KEY, code TEXT UNIQUE NOT NULL, requirement_id TEXT NOT NULL,
          state TEXT NOT NULL, name TEXT NOT NULL, marker TEXT NOT NULL,
          created_at REAL NOT NULL, updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS strategy_events (
          event_id INTEGER PRIMARY KEY AUTOINCREMENT, strategy_id TEXT NOT NULL,
          from_state TEXT, to_state TEXT NOT NULL, created_at REAL NOT NULL
        );
        """)
        self.connection.commit()

    def close(self):
        self.connection.close()

    def publish(self, requirement_id: str, name: str, marker: str) -> dict[str, Any]:
        if not requirement_id or not name:
            raise ValueError("requirement_id and name are required")
        existing = self.connection.execute("SELECT * FROM strategies WHERE requirement_id=? AND marker=?",
                                           (requirement_id, marker)).fetchone()
        if existing:
            return dict(existing)
        strategy_id = "str-" + uuid.uuid4().hex[:12]
        code = "STR-" + uuid.uuid4().hex[:10].upper()
        now = time.time()
        self.connection.execute("INSERT INTO strategies VALUES(?,?,?,?,?,?,?,?)",
                                (strategy_id, code, requirement_id, "PUBLISHED", name, marker, now, now))
        self.connection.execute("INSERT INTO strategy_events(strategy_id,to_state,created_at) VALUES(?,?,?)",
                                (strategy_id, "PUBLISHED", now))
        self.connection.commit()
        return self.get(strategy_id)

    def get(self, strategy_id: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM strategies WHERE id=?", (strategy_id,)).fetchone()
        if not row:
            raise KeyError(strategy_id)
        return dict(row)

    def cancel(self, strategy_id: str) -> dict[str, Any]:
        row = self.get(strategy_id)
        if row["state"] != "CANCELLED":
            now = time.time()
            self.connection.execute("UPDATE strategies SET state=?,updated_at=? WHERE id=?",
                                    ("CANCELLED", now, strategy_id))
            self.connection.execute("INSERT INTO strategy_events(strategy_id,from_state,to_state,created_at) VALUES(?,?,?,?)",
                                    (strategy_id, row["state"], "CANCELLED", now))
            self.connection.commit()
        return self.get(strategy_id)

    def residue(self, marker: str) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM strategies WHERE marker=? AND state!='CANCELLED'",
                                           (marker,)).fetchone()[0])


def build_strategy_pack(store: MockStrategyStore) -> CapabilityPack:
    pack = CapabilityPack("mock-strategy", "1.0.0")

    def publish(inputs, context):
        requirement = context.get("requirement") or {}
        row = store.publish(str(inputs.get("requirement_id") or requirement.get("id") or ""),
                            str(inputs.get("name") or "AUTO-STRATEGY"),
                            str(inputs.get("marker") or context.get("marker") or ""))
        return {"outputs": {"strategy": row, "strategy.id": row["id"], "strategy.code": row["code"],
                             "strategy.state": row["state"]},
                "evidence": {"api": {"status": 201, "data": row}, "db": row}}

    def cancel(inputs, context):
        strategy = context.get("strategy") or {}
        row = store.cancel(str(inputs.get("strategy_id") or strategy.get("id")))
        return {"outputs": {"strategy.state": row["state"]}, "evidence": {"db": row}, "status": "compensated"}

    pack.register("strategy.publish", publish, compensator=cancel, evidence=["api", "db"])
    pack.register("strategy.cancel", cancel, evidence=["db"])
    return pack
