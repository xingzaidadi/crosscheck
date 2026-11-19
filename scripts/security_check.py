"""Run dependency and Python security checks with reproducible exit codes."""
from __future__ import annotations

import argparse
import subprocess
import sys


def commands(*, skip_dependencies: bool = False) -> list[list[str]]:
    result = []
    if not skip_dependencies:
        result.append([sys.executable, "-m", "pip_audit", "-r", "requirements.lock", "--strict"])
    result.append([sys.executable, "-m", "bandit", "-r", "core", "adapters", "db", "scripts", "-lll"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="运行 pip-audit 和 bandit 安全门禁")
    parser.add_argument("--skip-dependencies", action="store_true")
    args = parser.parse_args()
    for command in commands(skip_dependencies=args.skip_dependencies):
        print("$", " ".join(command))
        result = subprocess.run(command)
        if result.returncode:
            return result.returncode
    print("security checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
