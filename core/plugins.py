"""Small, explicit extension contracts for non-core protocols and databases.

Plugins are intentionally not auto-trusted. A workspace may register an
adapter, but canonical compilation still requires a matching connector and
the normal approval/evidence/cleanup gates.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PluginResult:
    ok: bool
    status: str = ""
    request: dict[str, Any] = field(default_factory=dict)
    response: Any = None
    evidence: list[str] = field(default_factory=list)
    error: str | None = None


class ProtocolPlugin(ABC):
    kind = ""

    @abstractmethod
    def execute(self, action: dict[str, Any], variables: dict[str, Any]) -> PluginResult:
        """Execute one action and return machine-readable evidence."""

    @abstractmethod
    def close(self) -> None:
        """Release clients, connections and background resources."""


class DatabasePlugin(ABC):
    dialect = ""

    @abstractmethod
    def inspect(self) -> dict[str, Any]:
        """Return schema evidence without business-specific assumptions."""

    @abstractmethod
    def close(self) -> None:
        """Release database resources."""


_protocols: dict[str, type[ProtocolPlugin]] = {}
_databases: dict[str, type[DatabasePlugin]] = {}


def register_protocol(kind: str, plugin: type[ProtocolPlugin]) -> None:
    if not kind or not issubclass(plugin, ProtocolPlugin):
        raise TypeError("protocol plugin must be a ProtocolPlugin subclass")
    _protocols[kind] = plugin


def register_database(dialect: str, plugin: type[DatabasePlugin]) -> None:
    if not dialect or not issubclass(plugin, DatabasePlugin):
        raise TypeError("database plugin must be a DatabasePlugin subclass")
    _databases[dialect] = plugin


def protocol_plugins() -> tuple[str, ...]:
    return tuple(sorted(_protocols))


def database_plugins() -> tuple[str, ...]:
    return tuple(sorted(_databases))
