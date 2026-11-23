"""The public CLI exposes stable product commands and safe scaffolding."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    help_result = subprocess.run([sys.executable, "crosscheck_cli.py", "--help"], cwd=ROOT,
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert help_result.returncode == 0
    for command in ("doctor", "init", "onboard", "plan", "run", "knowledge", "dashboard", "map",
                    "readiness", "product-readiness", "product-remediation", "product-remediation-review",
                    "asset-health", "asset-recertify", "quality-gate", "domain-capability", "soak-report",
                    "self-test", "demo", "release", "task"):
        assert command in help_result.stdout
    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory) / "workspace"
        result = subprocess.run([sys.executable, "crosscheck_cli.py", "init", str(workspace)], cwd=ROOT)
        assert result.returncode == 0
        assert (workspace / "knowledge_base" / "decisions").is_dir()
        assert (workspace / "suites").is_dir()
        assert (workspace / "config" / "db.example.yaml").is_file()
        assert (workspace / "profiles" / "_example.yaml").is_file()
        assert (workspace / "suites" / "_suite.example.yaml").is_file()
        assert (workspace / "plugins").is_dir()
        assert (workspace / "plugins" / "plugin.example.py").is_file()
    print("product CLI passed")


def test_cli_subcommand_can_import_repository_packages() -> None:
    result = subprocess.run(
        [sys.executable, "crosscheck_cli.py", "mock-requirement"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stderr


if __name__ == "__main__":
    main()
