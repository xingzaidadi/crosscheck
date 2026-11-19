"""Release policy is allowlist-based and rejects workspace and secret content."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.build_release import (REQUIRED_RELEASE_FILES, REQUIRED_RELEASE_RESOURCES, content_secret_reason, repository_state,
                                   tracked_files, unsafe_reason)  # noqa: E402


def main() -> None:
    assert unsafe_reason("core/engine.py") is None
    assert unsafe_reason("crosscheck_cli.py") is None
    assert unsafe_reason("pyproject.toml") is None
    assert unsafe_reason("workspace/config/db.yaml")
    assert unsafe_reason("random-root/file.txt")
    assert "docs/COMPATIBILITY.md" in REQUIRED_RELEASE_FILES
    assert "templates/plugin.example.py" in REQUIRED_RELEASE_RESOURCES
    with patch("scripts.build_release.subprocess.check_output", return_value=b"core/engine.py\0"):
        assert tracked_files() == ["core/engine.py"]
    with patch("scripts.build_release.subprocess.check_output", side_effect=["abc123\n", " M README.md\n"]):
        assert repository_state() == {"commit": "abc123", "dirty": [" M README.md"]}
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "secret.txt"
        path.write_text("client_secret: abc", encoding="utf-8")
        assert content_secret_reason(path)
    print("release policy passed")


if __name__ == "__main__":
    main()
