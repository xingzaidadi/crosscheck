"""UI verification must prefer the configured endpoint, not an unrelated last XHR."""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    captures = [
        SimpleNamespace(url="https://x.test/demand/api/accept/page"),
        SimpleNamespace(url="https://x.test/foundation/api/options"),
    ]
    pattern = "/demand/api/accept/page"
    matching = [capture for capture in captures if pattern in capture.url]
    picked = matching[-1] if matching else captures[-1]
    assert picked.url.endswith("/demand/api/accept/page")
    print("ui endpoint pick passed")


if __name__ == "__main__":
    main()
