"""Filesystem-backed asset registry with atomic state transitions."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .asset_pipeline import can_execute, promote


class AssetStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, asset_id: str) -> Path:
        safe = "".join(char for char in str(asset_id) if char.isalnum() or char in "._-")
        if not safe:
            raise ValueError("asset_id is required")
        return self.root / f"{safe}.json"

    def save(self, asset: dict[str, Any]) -> Path:
        path = self.path(str(asset.get("asset_id") or ""))
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asset, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
        return path

    def load(self, asset_id: str) -> dict[str, Any]:
        path = self.path(asset_id)
        if not path.is_file():
            raise FileNotFoundError(asset_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def promote(self, asset_id: str, target: str, *, evidence: list[str] | None = None) -> dict[str, Any]:
        updated = promote(self.load(asset_id), target, evidence=evidence)
        self.save(updated)
        return updated

    def list(self, *, state: str | None = None) -> list[dict[str, Any]]:
        rows = []
        for path in sorted(self.root.glob("*.json")):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if state is None or item.get("state") == state:
                rows.append(item)
        return rows

    def executable(self, asset_id: str) -> bool:
        return can_execute(self.load(asset_id))

    def retire_drifted(self, *, max_drift_rate: float = 0.2) -> list[str]:
        retired = []
        for asset in self.list():
            if asset.get("state") == "retired":
                continue
            if float(asset.get("drift_rate") or 0) > max_drift_rate:
                asset["state"] = "retired"
                asset["retired_reason"] = "drift_rate_exceeded"
                self.save(asset)
                retired.append(str(asset["asset_id"]))
        return retired
