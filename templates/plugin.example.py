"""Workspace plugin example; copy into <workspace>/plugins/ and review it."""
from core.plugins import ProtocolPlugin, PluginResult


class ExampleProtocolPlugin(ProtocolPlugin):
    kind = "example"

    def execute(self, action, variables):
        # Replace this with a trusted client. Never mark a case PASS without
        # independent response assertions and a cleanup strategy.
        return PluginResult(ok=False, error="example plugin is a scaffold")

    def close(self):
        return None
