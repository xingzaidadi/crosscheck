"""Deterministic local requirement capability pack for G3 acceptance."""
from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from .business_capabilities import CapabilityPack


STATES = ("DRAFT", "SUBMITTED", "APPROVED", "VERIFIED", "CANCELLED")
TRANSITIONS = {"DRAFT": {"SUBMITTED", "CANCELLED"}, "SUBMITTED": {"APPROVED", "CANCELLED"},
               "APPROVED": {"VERIFIED", "CANCELLED"}, "VERIFIED": {"CANCELLED"}, "CANCELLED": set()}


class MockRequirementStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS requirements (
          id TEXT PRIMARY KEY, code TEXT UNIQUE NOT NULL, state TEXT NOT NULL,
          amount REAL NOT NULL, department TEXT NOT NULL, marker TEXT NOT NULL,
          created_at REAL NOT NULL, updated_at REAL NOT NULL, cancelled_at REAL
        );
        CREATE TABLE IF NOT EXISTS requirement_events (
          event_id INTEGER PRIMARY KEY AUTOINCREMENT, requirement_id TEXT NOT NULL,
          from_state TEXT, to_state TEXT NOT NULL, created_at REAL NOT NULL
        );
        """)
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def create(self, *, amount: float, department: str, marker: str) -> dict[str, Any]:
        if amount <= 0 or not department:
            raise ValueError("amount and department are required")
        requirement_id = "req-" + uuid.uuid4().hex[:12]
        code = "REQ-" + uuid.uuid4().hex[:10].upper()
        now = time.time()
        self.connection.execute("INSERT INTO requirements VALUES(?,?,?,?,?,?,?,?,?)",
                                (requirement_id, code, "DRAFT", amount, department, marker, now, now, None))
        self.connection.execute("INSERT INTO requirement_events(requirement_id,to_state,created_at) VALUES(?,?,?)",
                                (requirement_id, "DRAFT", now))
        self.connection.commit()
        return self.get(requirement_id)

    def find(self, *, state: str | None = None, marker: str | None = None) -> dict[str, Any] | None:
        query = "SELECT * FROM requirements WHERE 1=1"
        params: list[Any] = []
        if state:
            query += " AND state=?"; params.append(state)
        if marker:
            query += " AND marker=?"; params.append(marker)
        query += " ORDER BY created_at DESC LIMIT 1"
        row = self.connection.execute(query, params).fetchone()
        return dict(row) if row else None

    def get(self, requirement_id: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM requirements WHERE id=?", (requirement_id,)).fetchone()
        if not row:
            raise KeyError(requirement_id)
        return dict(row)

    def transition(self, requirement_id: str, target: str) -> dict[str, Any]:
        current = self.get(requirement_id)
        if target not in STATES or target not in TRANSITIONS[current["state"]]:
            raise ValueError(f"invalid requirement transition: {current['state']} -> {target}")
        now = time.time()
        cancelled_at = now if target == "CANCELLED" else current["cancelled_at"]
        self.connection.execute("UPDATE requirements SET state=?,updated_at=?,cancelled_at=? WHERE id=?",
                                (target, now, cancelled_at, requirement_id))
        self.connection.execute("INSERT INTO requirement_events(requirement_id,from_state,to_state,created_at) VALUES(?,?,?,?)",
                                (requirement_id, current["state"], target, now))
        self.connection.commit()
        return self.get(requirement_id)

    def residue(self, marker: str) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM requirements WHERE marker=?", (marker,)).fetchone()[0])

    def cleanup(self, marker: str) -> int:
        cursor = self.connection.execute("DELETE FROM requirements WHERE marker=?", (marker,))
        self.connection.commit()
        return int(cursor.rowcount)


def build_pack(store: MockRequirementStore) -> CapabilityPack:
    pack = CapabilityPack("mock-requirement", "1.0.0")

    def create(inputs, context):
        row = store.create(amount=float(inputs["amount"]), department=str(inputs["department"]),
                           marker=str(inputs.get("marker") or context.get("marker") or ""))
        return {"outputs": {"requirement": row, "requirement.id": row["id"], "requirement.code": row["code"],
                             "requirement.state": row["state"]},
                "evidence": {"api": {"status": 201, "data": row}, "db": row}}

    def find(inputs, context):
        row = store.find(state=inputs.get("state"), marker=inputs.get("marker") or context.get("marker"))
        return {"outputs": {"requirement": row, "requirement.id": row["id"] if row else None},
                "evidence": {"api": {"status": 200, "data": row}, "db": row or {}}}

    def move(target):
        def handler(inputs, context):
            requirement_id = inputs.get("requirement_id") or context.get("requirement.id")
            row = store.transition(str(requirement_id), target)
            return {"outputs": {"requirement": row, "requirement.state": row["state"]},
                    "evidence": {"api": {"status": 200, "data": row}, "db": row}}
        return handler

    def cancel(inputs, context):
        requirement_id = inputs.get("requirement_id") or context.get("requirement.id")
        row = store.get(str(requirement_id))
        if row["state"] != "CANCELLED":
            row = store.transition(str(requirement_id), "CANCELLED")
        return {"outputs": {"requirement.state": row["state"]}, "evidence": {"db": row}}

    def cleanup(inputs, context):
        marker = str(inputs.get("marker") or context.get("marker") or "")
        return {"outputs": {"cleanup.count": store.cleanup(marker)}, "status": "compensated"}

    pack.register("requirement.create", create, compensator=cleanup, evidence=["api", "db"])
    pack.register("requirement.find", find, evidence=["api", "db"])
    pack.register("requirement.submit", move("SUBMITTED"), compensator=cleanup, evidence=["api", "db"])
    pack.register("requirement.approve", move("APPROVED"), compensator=cleanup, evidence=["api", "db"])
    pack.register("requirement.verify", move("VERIFIED"), compensator=cleanup, evidence=["api", "db"])
    pack.register("requirement.cancel", cancel, evidence=["db"])
    return pack
