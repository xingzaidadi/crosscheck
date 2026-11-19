"""The public Playwright adapter uses the same deterministic Prober execution path."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.playwright_adapter import PlaywrightAdapter  # noqa: E402
from core.interfaces import Expected, TestCase  # noqa: E402
from core.prober import Capture  # noqa: E402


class FakeKnowledge:
    def page_model(self, feature):
        assert feature == "create"
        return {"entry": "https://example.invalid/create", "url_pattern": "/api/create",
                "actions": [{"action": "text", "label": "名称", "value": "{{marker}}"}],
                "require_write_call": True}


class FakeProber:
    last_actions = None

    def __init__(self, **kwargs):
        self.replay_results = []

    def probe(self, page_url, **kwargs):
        assert page_url.endswith("/create")
        FakeProber.last_actions = kwargs["replay_actions"]
        self.replay_results = [{"ok": True, "action": "text", "target": "名称"}]

    def pick_write_call(self):
        return Capture(url="https://example.invalid/api/create", method="POST",
                       resource_type="xhr", status=201, response_json={"id": 1})


def main() -> None:
    case = TestCase("C1", "create", "operator", None, [], Expected())
    adapter = PlaywrightAdapter(FakeKnowledge())
    with patch("adapters.playwright_adapter.Prober", FakeProber):
        adapter.setup(case)
        result = adapter.perform(case, "AUTOTEST_C1")
        adapter.teardown()
    assert result.ok and result.api_status == 201 and result.api_body == {"id": 1}
    assert FakeProber.last_actions[0]["value"] == "AUTOTEST_C1"
    print("playwright adapter passed")


if __name__ == "__main__":
    main()
