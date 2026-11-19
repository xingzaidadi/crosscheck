"""Execution variable and object lineage tracking."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class LineageEntry:
    variable: str
    value: Any
    capability: str
    parent_variables: tuple[str, ...] = ()


class Lineage:
    def __init__(self):
        self.entries: dict[str, LineageEntry] = {}

    def capture(self, outputs: dict[str, Any], *, capability: str, parent_variables: tuple[str, ...] = ()) -> None:
        for name, value in outputs.items():
            self.entries[str(name)] = LineageEntry(str(name), value, capability, parent_variables)

    def resolve(self, variable: str) -> Any:
        if variable not in self.entries:
            raise KeyError(f"unknown output variable: {variable}")
        return self.entries[variable].value

    def export(self) -> list[dict[str, Any]]:
        return [asdict(entry) for entry in self.entries.values()]
