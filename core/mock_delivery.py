"""Local sourcing/contract/order capability pack for the G5 slice."""
from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from .business_capabilities import CapabilityPack


class MockDeliveryStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS sourcing (
          id TEXT PRIMARY KEY, code TEXT UNIQUE NOT NULL, strategy_id TEXT NOT NULL,
          state TEXT NOT NULL, marker TEXT NOT NULL, created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS contracts (
          id TEXT PRIMARY KEY, code TEXT UNIQUE NOT NULL, sourcing_id TEXT NOT NULL,
          state TEXT NOT NULL, amount REAL NOT NULL, marker TEXT NOT NULL, created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS orders (
          id TEXT PRIMARY KEY, code TEXT UNIQUE NOT NULL, contract_id TEXT NOT NULL,
          state TEXT NOT NULL, quantity INTEGER NOT NULL, amount REAL NOT NULL,
          marker TEXT NOT NULL, created_at REAL NOT NULL
        );
        """)
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def publish_sourcing(self, strategy_id: str, marker: str) -> dict[str, Any]:
        existing = self.connection.execute("SELECT * FROM sourcing WHERE strategy_id=? AND marker=?",
                                           (strategy_id, marker)).fetchone()
        if existing:
            return dict(existing)
        row = ("src-" + uuid.uuid4().hex[:12], "SRC-" + uuid.uuid4().hex[:10].upper(),
               strategy_id, "PUBLISHED", marker, time.time())
        self.connection.execute("INSERT INTO sourcing VALUES(?,?,?,?,?,?)", row)
        self.connection.commit()
        return self.get_sourcing(row[0])

    def sign_contract(self, sourcing_id: str, amount: float, marker: str) -> dict[str, Any]:
        existing = self.connection.execute("SELECT * FROM contracts WHERE sourcing_id=? AND marker=?",
                                           (sourcing_id, marker)).fetchone()
        if existing:
            return dict(existing)
        if amount <= 0:
            raise ValueError("contract amount must be positive")
        row = ("ctr-" + uuid.uuid4().hex[:12], "CTR-" + uuid.uuid4().hex[:10].upper(),
               sourcing_id, "SIGNED", amount, marker, time.time())
        self.connection.execute("INSERT INTO contracts VALUES(?,?,?,?,?,?,?)", row)
        self.connection.commit()
        return self.get_contract(row[0])

    def create_order(self, contract_id: str, quantity: int, amount: float, marker: str) -> dict[str, Any]:
        existing = self.connection.execute("SELECT * FROM orders WHERE contract_id=? AND marker=?",
                                           (contract_id, marker)).fetchone()
        if existing:
            return dict(existing)
        if quantity <= 0 or amount <= 0:
            raise ValueError("order quantity and amount must be positive")
        row = ("ord-" + uuid.uuid4().hex[:12], "ORD-" + uuid.uuid4().hex[:10].upper(),
               contract_id, "CREATED", quantity, amount, marker, time.time())
        self.connection.execute("INSERT INTO orders VALUES(?,?,?,?,?,?,?,?)", row)
        self.connection.commit()
        return self.get_order(row[0])

    def get_sourcing(self, item_id: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM sourcing WHERE id=?", (item_id,)).fetchone()
        if not row:
            raise KeyError(item_id)
        return dict(row)

    def get_contract(self, item_id: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM contracts WHERE id=?", (item_id,)).fetchone()
        if not row:
            raise KeyError(item_id)
        return dict(row)

    def get_order(self, item_id: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM orders WHERE id=?", (item_id,)).fetchone()
        if not row:
            raise KeyError(item_id)
        return dict(row)

    def cancel_all(self, marker: str) -> dict[str, int]:
        counts = {}
        for table in ("orders", "contracts", "sourcing"):
            cursor = self.connection.execute(f"DELETE FROM {table} WHERE marker=?", (marker,))
            counts[table] = int(cursor.rowcount)
        self.connection.commit()
        return counts

    def residue(self, marker: str) -> int:
        return sum(int(self.connection.execute(f"SELECT COUNT(*) FROM {table} WHERE marker=?", (marker,)).fetchone()[0])
                   for table in ("orders", "contracts", "sourcing"))

    def counts(self, marker: str) -> dict[str, int]:
        return {table: int(self.connection.execute(f"SELECT COUNT(*) FROM {table} WHERE marker=?", (marker,)).fetchone()[0])
                for table in ("sourcing", "contracts", "orders")}


def build_delivery_pack(store: MockDeliveryStore) -> CapabilityPack:
    pack = CapabilityPack("mock-delivery", "1.0.0")

    def publish(inputs, context):
        strategy = context.get("strategy") or {}
        row = store.publish_sourcing(str(inputs.get("strategy_id") or strategy.get("id") or ""),
                                     str(inputs.get("marker") or context.get("marker") or ""))
        return {"outputs": {"sourcing": row, "sourcing.id": row["id"], "sourcing.state": row["state"],
                             "sourcing.strategy_id": row["strategy_id"]},
                "evidence": {"api": {"status": 201, "data": row}, "db": row}}

    def sign(inputs, context):
        sourcing = context.get("sourcing") or {}
        row = store.sign_contract(str(inputs.get("sourcing_id") or sourcing.get("id") or ""),
                                  float(inputs.get("amount") or 1), str(inputs.get("marker") or context.get("marker") or ""))
        return {"outputs": {"contract": row, "contract.id": row["id"], "contract.state": row["state"],
                             "contract.sourcing_id": row["sourcing_id"]},
                "evidence": {"api": {"status": 201, "data": row}, "db": row}}

    def order(inputs, context):
        contract = context.get("contract") or {}
        row = store.create_order(str(inputs.get("contract_id") or contract.get("id") or ""),
                                 int(inputs.get("quantity") or 1), float(inputs.get("amount") or 1),
                                 str(inputs.get("marker") or context.get("marker") or ""))
        return {"outputs": {"order": row, "order.id": row["id"], "order.state": row["state"],
                             "order.contract_id": row["contract_id"]},
                "evidence": {"api": {"status": 201, "data": row}, "db": row}}

    def compensate(inputs, context):
        counts = store.cancel_all(str(inputs.get("marker") or context.get("marker") or ""))
        return {"outputs": {"cleanup": counts}, "status": "compensated"}

    pack.register("sourcing.publish", publish, compensator=compensate, evidence=["api", "db"])
    pack.register("contract.sign", sign, compensator=compensate, evidence=["api", "db"])
    pack.register("order.create", order, compensator=compensate, evidence=["api", "db"])
    return pack
