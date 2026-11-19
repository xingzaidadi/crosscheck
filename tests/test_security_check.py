"""Security command is wired to the documented tools."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.security_check import commands  # noqa: E402


def main() -> None:
    full = commands()
    python_only = commands(skip_dependencies=True)
    assert any("pip_audit" in command and "requirements.lock" in command for command in full)
    assert any("bandit" in command for command in full)
    assert len(python_only) == 1 and "bandit" in python_only[0]
    print("security check wiring passed")


if __name__ == "__main__":
    main()
