"""Transactional registry for arsenal runs, objects, leases and steps."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class RunRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self._create_schema()

    def _create_schema(self) -> None:
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
          run_id TEXT PRIMARY KEY, plan_hash TEXT NOT NULL, status TEXT NOT NULL,
          environment TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS objects (
          object_key TEXT PRIMARY KEY, object_type TEXT NOT NULL, identity_json TEXT NOT NULL,
          state TEXT NOT NULL, attributes_json TEXT NOT NULL, provenance_json TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'active', created_at REAL NOT NULL, updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS leases (
          lease_id TEXT PRIMARY KEY, object_key TEXT NOT NULL REFERENCES objects(object_key),
          run_id TEXT NOT NULL REFERENCES runs(run_id), expires_at REAL NOT NULL,
          status TEXT NOT NULL DEFAULT 'active', created_at REAL NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_lease_per_object
          ON leases(object_key) WHERE status='active';
        CREATE TABLE IF NOT EXISTS steps (
          run_id TEXT NOT NULL REFERENCES runs(run_id), step_id TEXT NOT NULL,
          capability_ref TEXT NOT NULL, state TEXT NOT NULL, detail TEXT NOT NULL,
          updated_at REAL NOT NULL, PRIMARY KEY(run_id, step_id)
        );
        CREATE TABLE IF NOT EXISTS audit_events (
          event_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
          event_type TEXT NOT NULL, payload_json TEXT NOT NULL, created_at REAL NOT NULL
        );
        """)

    def close(self) -> None:
        self.connection.close()

    def create_run(self, run_id: str, plan_hash: str, environment: str) -> None:
        now = time.time()
        with self.connection:
            self.connection.execute(
                "INSERT INTO runs(run_id,plan_hash,status,environment,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (run_id, plan_hash, "running", environment, now, now))
            self.event(run_id, "run_created", {"plan_hash": plan_hash, "environment": environment})

    def set_run_status(self, run_id: str, status: str) -> None:
        with self.connection:
            self.connection.execute("UPDATE runs SET status=?,updated_at=? WHERE run_id=?",
                                    (status, time.time(), run_id))
            self.event(run_id, "run_status", {"status": status})

    def register_object(self, object_key: str, object_type: str, identity: dict[str, Any],
                        state: str, attributes: dict[str, Any] | None = None,
                        provenance: dict[str, Any] | None = None) -> None:
        now = time.time()
        with self.connection:
            self.connection.execute(
                "INSERT INTO objects(object_key,object_type,identity_json,state,attributes_json,provenance_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (object_key, object_type, _json(identity), state, _json(attributes or {}),
                 _json(provenance or {}), now, now))

    def claim_lease(self, object_key: str, lease_id: str, run_id: str, ttl_s: float = 900) -> None:
        now = time.time()
        with self.connection:
            self.connection.execute("DELETE FROM leases WHERE status='active' AND expires_at<=?", (now,))
            try:
                self.connection.execute(
                    "INSERT INTO leases(lease_id,object_key,run_id,expires_at,created_at) VALUES(?,?,?,?,?)",
                    (lease_id, object_key, run_id, now + ttl_s, now))
            except sqlite3.IntegrityError as exc:
                raise RuntimeError(f"object lease conflict: {object_key}") from exc
            self.event(run_id, "lease_claimed", {"object_key": object_key, "lease_id": lease_id})

    def release_lease(self, lease_id: str, run_id: str) -> None:
        with self.connection:
            self.connection.execute("UPDATE leases SET status='released' WHERE lease_id=? AND run_id=?",
                                    (lease_id, run_id))
            self.event(run_id, "lease_released", {"lease_id": lease_id})

    def save_step(self, run_id: str, step_id: str, capability_ref: str, state: str,
                  detail: str = "") -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO steps(run_id,step_id,capability_ref,state,detail,updated_at) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(run_id,step_id) DO UPDATE SET state=excluded.state,detail=excluded.detail,updated_at=excluded.updated_at",
                (run_id, step_id, capability_ref, state, detail, time.time()))
            self.event(run_id, "step_state", {"step_id": step_id, "state": state, "detail": detail})

    def recoverable_steps(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT step_id,capability_ref,state,detail FROM steps WHERE run_id=? AND state IN ('unknown','running') ORDER BY step_id",
            (run_id,)).fetchall()
        return [dict(row) for row in rows]

    def run(self, run_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT run_id,plan_hash,status,environment,created_at,updated_at FROM runs WHERE run_id=?",
            (run_id,)).fetchone()
        return dict(row) if row else None

    def steps(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT step_id,capability_ref,state,detail,updated_at FROM steps WHERE run_id=? ORDER BY step_id",
            (run_id,)).fetchall()
        return [dict(row) for row in rows]

    def event(self, run_id: str, event_type: str, payload: dict[str, Any]) -> None:
        self.connection.execute(
            "INSERT INTO audit_events(run_id,event_type,payload_json,created_at) VALUES(?,?,?,?)",
            (run_id, event_type, _json(payload), time.time()))

    def audit_events(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT event_type,payload_json,created_at FROM audit_events WHERE run_id=? ORDER BY event_id",
            (run_id,)).fetchall()
        return [{"event_type": row["event_type"], "payload": json.loads(row["payload_json"]),
                 "created_at": row["created_at"]} for row in rows]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
