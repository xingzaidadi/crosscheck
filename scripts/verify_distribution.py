"""Build a wheel, install it into a clean venv, and exercise the public CLI."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def run(command: list[str], *, cwd: Path = ROOT) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="在干净虚拟环境验收 wheel 和公开 CLI")
    parser.add_argument("--skip-demo", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="crosscheck-dist-") as directory:
        root = Path(directory)
        wheel_dir = root / "wheel"
        # Keep build isolation enabled: a clean verifier is intentionally not
        # required to have setuptools installed in its calling environment.
        run([sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-w", str(wheel_dir)])
        wheel = next(wheel_dir.glob("crosscheck_agent-*.whl"))
        environment = root / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        run([str(python), "-m", "pip", "install", str(wheel)])
        run([str(python), "-m", "playwright", "install", "chromium"])
        workspace = root / "workspace"
        run([str(python), "-m", "crosscheck_cli", "doctor"])
        run([str(python), "-m", "crosscheck_cli", "init", str(workspace)])
        resource_check = (
            "import importlib.resources as r, crosscheck_templates; "
            "names={x.name for x in r.files(crosscheck_templates).iterdir()}; "
            "assert {'profile.example.yaml','suite.example.yaml','case.example.yaml','ui_semantics.yaml'} <= names"
        )
        run([str(python), "-c", resource_check])
        run([str(python), "-m", "crosscheck_cli", "ui-run", "--help"])
        run([str(python), "-m", "crosscheck_cli", "ui-gap-audit", "--help"])
        if not args.skip_demo:
            run([str(python), "-m", "crosscheck_cli", "demo", "--workspace", str(root / "demo")])
        result = {"wheel": wheel.name, "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                  "doctor": "pass", "init": "pass", "ui_cli": "pass",
                  "demo": "skipped" if args.skip_demo else "pass"}
        output = ROOT / "dist" / "distribution-verification.json"
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"OK: distribution verification: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
