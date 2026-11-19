"""External acceptance evidence cannot be replaced by compile-only simulations."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.external_acceptance import validate  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        evidence = root / "evidence"
        evidence.mkdir()
        for name in ("a", "b"):
            (evidence / f"{name}.json").write_text(
                json.dumps({"total": 2, "passed": 2, "failed": 0, "blocked": 0}), encoding="utf-8")
        manifest = {"systems": [
            {"id": "a", "business_domain": "inventory", "base_url": "https://a.test",
             "auth_mode": "credential", "ui_kit": "antd", "database": "mysql",
             "verified_layers": ["ui", "api", "db"], "run_report": "evidence/a.json"},
            {"id": "b", "business_domain": "billing", "base_url": "https://b.test",
             "auth_mode": "sso", "ui_kit": "element", "database": "mysql",
             "verified_layers": ["ui", "api", "db"], "run_report": "evidence/b.json"}]}
        path = root / "manifest.yaml"
        path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
        assert validate(path) == []
        manifest["systems"] = manifest["systems"][:1]
        path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
        assert validate(path)
    print("external acceptance contract passed")


if __name__ == "__main__":
    main()
