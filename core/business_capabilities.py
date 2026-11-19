"""Business-neutral adapters for declarative business capability packs."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class CapabilityPack:
    name: str
    version: str
    handlers: dict[str, Callable[..., dict[str, Any]]] = field(default_factory=dict)
    compensators: dict[str, Callable[..., dict[str, Any]]] = field(default_factory=dict)
    evidence: dict[str, list[str]] = field(default_factory=dict)

    def register(self, capability: str, handler: Callable[..., dict[str, Any]], *,
                 compensator: Callable[..., dict[str, Any]] | None = None,
                 evidence: list[str] | None = None) -> None:
        if capability in self.handlers:
            raise ValueError(f"duplicate capability: {capability}")
        self.handlers[capability] = handler
        if compensator:
            self.compensators[capability] = compensator
        self.evidence[capability] = list(evidence or [])

    def validate(self, required: list[str]) -> list[str]:
        return [capability for capability in required if capability not in self.handlers]

    def execute(self, capability: str, *, inputs: dict[str, Any] | None = None,
                context: dict[str, Any] | None = None) -> dict[str, Any]:
        if capability not in self.handlers:
            raise KeyError(f"capability not registered: {capability}")
        result = dict(self.handlers[capability](inputs=dict(inputs or {}), context=dict(context or {})) or {})
        result.setdefault("capability", capability)
        result.setdefault("evidence", self.evidence.get(capability, []))
        return result

    def compensate(self, capability: str, *, inputs: dict[str, Any] | None = None,
                   context: dict[str, Any] | None = None) -> dict[str, Any]:
        handler = self.compensators.get(capability)
        if handler is None:
            return {"capability": capability, "status": "manual_required"}
        return dict(handler(inputs=dict(inputs or {}), context=dict(context or {})) or {})
