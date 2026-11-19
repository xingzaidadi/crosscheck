"""API retry refreshes the session once and leaves redacted request evidence."""
from __future__ import annotations

import os
import sys
from unittest.mock import Mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.api_adapter import ApiAdapter  # noqa: E402


class Response:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def main() -> None:
    refresh = Mock()
    adapter = ApiAdapter(base_url="https://example.test", refresh_session=refresh)
    client = Mock()
    client.request.side_effect = [Response(401, {"error": "expired"}), Response(200, {"ok": True})]
    client.cookies = {}
    adapter._client = client
    result = adapter.call({"method": "POST", "url": "/api/items",
                           "headers": {"Authorization": "secret", "X-Trace": "safe",
                                       "Idempotency-Key": "AUTOTEST_KEY"},
                           "body": {"name": "{{marker}}"}}, {"marker": "AUTOTEST_X"})
    assert result.ok and result.api_status == 200
    assert refresh.call_count == 1
    assert result.api_request["headers"]["Authorization"] == "<redacted>"
    assert result.api_request["body"]["name"] == "AUTOTEST_X"
    print("api refresh evidence passed")


if __name__ == "__main__":
    main()
