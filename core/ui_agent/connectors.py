"""Optional cross-layer connector façade for natural-language runs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_workspace_connector(workspace: str | Path, kind: str) -> dict[str, Any] | None:
    root = Path(workspace).resolve()
    candidates = {
        "db": [root / "config" / "db.yaml", root / "connectors" / "db.yaml"],
        "event": [root / "config" / "events.yaml", root / "connectors" / "events.yaml"],
        "mq": [root / "config" / "mq.yaml", root / "connectors" / "mq.yaml"],
    }.get(kind, [])
    for path in candidates:
        if not path.is_file():
            continue
        try:
            import yaml
            value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(value, dict):
                return {"kind": kind, "path": str(path), "config": value}
        except Exception:
            return None
    return None


def cross_layer_plan(workspace: str | Path, requested_layers: list[str]) -> dict[str, Any]:
    result = {}
    for layer in requested_layers:
        if layer == "ui":
            result[layer] = {"status": "AVAILABLE", "mode": "browser"}
        elif layer == "api":
            result[layer] = {"status": "AVAILABLE", "mode": "browser_network_capture"}
        elif layer in {"db", "event", "mq"}:
            connector = load_workspace_connector(workspace, layer)
            result[layer] = {
                "status": "READY" if connector else "NEEDS_CONFIG",
                "mode": "workspace_connector" if connector else "not_configured",
                "path": connector.get("path") if connector else "",
            }
    return result


def reconcile_ui_api(ui_text: str, api_payload: Any) -> dict[str, Any]:
    """Conservative shallow reconciliation for visible scalar API values."""
    body = json.dumps(api_payload, ensure_ascii=False, default=str) if not isinstance(api_payload, str) else api_payload
    tokens = [item for item in body.replace('"', " ").replace("'", " ").split() if len(item) >= 2]
    matched = [item for item in tokens if item in ui_text]
    return {"status": "PASSED" if matched else "INCONCLUSIVE", "matched_values": matched[:50],
            "message": "matched visible scalar values" if matched else "no conservative scalar match"}


def db_connector(workspace: str | Path):
    """Build a read-only DB client when the existing workspace config is valid."""
    from core.config import db_params, readonly_dsn
    from db.client import DbClient
    dsn = readonly_dsn()
    params = db_params("readonly")
    if not dsn and not params:
        return None
    return DbClient(dsn_readonly=dsn or None, readonly_params=params or None)


def db_scalar_check(workspace: str | Path, *, table: str, column: str, expected: Any,
                    where: str = "") -> dict[str, Any]:
    """Perform a validated, read-only scalar DB check."""
    from core.security import validate_sql_identifier
    validate_sql_identifier(table, label="table")
    validate_sql_identifier(column, label="column")
    client = db_connector(workspace)
    if client is None:
        return {"status": "NEEDS_CONFIG", "message": "read-only database connector is not configured"}
    try:
        query = f"SELECT {column} AS value FROM {table}"
        if where:
            query += f" WHERE {where}"
        query += " LIMIT 1"
        rows = client.query(query)
        actual = rows[0].get("value") if rows else None
        return {"status": "PASSED" if str(actual) == str(expected) else "FAILED",
                "actual": actual, "expected": expected, "table": table, "column": column}
    finally:
        client.close()


def event_connector(workspace: str | Path) -> dict[str, Any] | None:
    return load_workspace_connector(workspace, "event")


def event_readiness(workspace: str | Path, *, event_name: str = "") -> dict[str, Any]:
    connector = event_connector(workspace)
    if not connector:
        return {"status": "NEEDS_CONFIG", "message": "event/MQ connector is not configured", "event": event_name}
    return {"status": "READY", "message": "event connector is configured", "event": event_name,
            "path": connector["path"]}
