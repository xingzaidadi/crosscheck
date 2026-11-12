"""Release policy is allowlist-based and rejects workspace and secret content."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.build_release import content_secret_reason, unsafe_reason  # noqa: E402


def main() -> None:
    assert unsafe_reason("core/engine.py") is None
    assert unsafe_reason("workspace/config/db.yaml")
    assert unsafe_reason("random-root/file.txt")
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "secret.txt"
        path.write_text("client_secret: abc", encoding="utf-8")
        assert content_secret_reason(path)
    print("release policy passed")


if __name__ == "__main__":
    main()
