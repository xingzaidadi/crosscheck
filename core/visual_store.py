"""Visual baseline storage with explicit approval metadata."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


class VisualBaselineStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def record(self, component: str, image: str | Path, *, approver: str = "") -> dict[str, Any]:
        source = Path(image).resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        safe = "".join(char for char in component if char.isalnum() or char in "._-") or "component"
        target = self.root / f"{safe}.png"
        shutil.copyfile(source, target)
        metadata = {"component": component, "image": target.name, "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                    "approved": bool(approver), "approver": approver}
        (self.root / f"{safe}.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        return metadata

    def get(self, component: str) -> dict[str, Any]:
        safe = "".join(char for char in component if char.isalnum() or char in "._-") or "component"
        metadata_path = self.root / f"{safe}.json"
        if not metadata_path.is_file():
            raise FileNotFoundError(component)
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["path"] = str(self.root / metadata["image"])
        return metadata
