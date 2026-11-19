"""Safe declarative fixture creation and cleanup ledger for UI runs."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from core.fixtures import make_fixture


SUPPORTED_KINDS = {"txt", "csv", "bin"}


def provision_fixture(spec: dict[str, Any], run_dir: str | Path) -> dict[str, Any]:
    kind = str(spec.get("kind") or "txt")
    if kind not in SUPPORTED_KINDS:
        raise ValueError(f"unsupported fixture kind: {kind}")
    root = Path(run_dir).resolve() / "fixtures"
    root.mkdir(parents=True, exist_ok=True)
    marker = str(spec.get("marker") or "").strip()
    if len(marker) < 3:
        raise ValueError("fixture marker must contain at least 3 characters")
    path = make_fixture(kind, size_bytes=spec.get("size_bytes"), rows=int(spec.get("rows") or 0),
                        cols=int(spec.get("cols") or 3), dir=str(root),
                        name=str(spec.get("name") or f"{marker}.{kind}"))
    record = {"fixture_id": spec.get("fixture_id") or marker, "marker": marker,
              "path": str(path), "cleanup": "delete_file", "status": "PROVISIONED"}
    ledger = Path(run_dir) / "fixture_ledger.json"
    rows = json.loads(ledger.read_text(encoding="utf-8")) if ledger.exists() else []
    rows.append(record)
    ledger.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def cleanup_fixtures(run_dir: str | Path) -> dict[str, Any]:
    root = Path(run_dir).resolve()
    ledger = root / "fixture_ledger.json"
    rows = json.loads(ledger.read_text(encoding="utf-8")) if ledger.exists() else []
    cleaned, failed = [], []
    fixture_root = (root / "fixtures").resolve()
    for row in rows:
        path = Path(str(row.get("path") or "")).resolve()
        try:
            path.relative_to(fixture_root)
            if path.is_file():
                path.unlink()
            row["status"] = "CLEANED"
            cleaned.append(row.get("fixture_id"))
        except (ValueError, OSError) as exc:
            row["status"] = "CLEANUP_FAILED"
            row["error"] = str(exc)
            failed.append(row.get("fixture_id"))
    if fixture_root.is_dir() and not any(fixture_root.iterdir()):
        shutil.rmtree(fixture_root)
    ledger.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"cleaned": cleaned, "failed": failed, "residue": bool(failed)}

