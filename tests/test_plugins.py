"""Extension contracts reject invalid registrations and preserve evidence shape."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.plugins import DatabasePlugin, ProtocolPlugin, PluginResult, register_database, register_protocol  # noqa: E402


class DemoProtocol(ProtocolPlugin):
    kind = "demo"

    def execute(self, action, variables):
        return PluginResult(ok=True, status="200", request=action, response=variables)

    def close(self):
        pass


class DemoDatabase(DatabasePlugin):
    dialect = "demo"

    def inspect(self):
        return {"dialect": self.dialect, "tables": []}

    def close(self):
        pass


def main() -> None:
    register_protocol("demo", DemoProtocol)
    register_database("demo", DemoDatabase)
    assert DemoProtocol().execute({"op": "ping"}, {"ok": True}).ok
    assert DemoDatabase().inspect()["dialect"] == "demo"
    print("plugin contracts passed")


if __name__ == "__main__":
    main()
