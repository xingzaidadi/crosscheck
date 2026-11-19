"""Plugin contracts for external events, object storage and callbacks."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExternalResult:
    ok: bool
    evidence: list[str] = field(default_factory=list)
    output: dict[str, Any] = field(default_factory=dict)
    error: str = ""


class EventAdapter(ABC):
    @abstractmethod
    def publish(self, topic: str, payload: dict[str, Any], *, idempotency_key: str) -> ExternalResult:
        raise NotImplementedError

    @abstractmethod
    def wait_consumed(self, correlation_id: str, *, timeout_s: float) -> ExternalResult:
        raise NotImplementedError


class ObjectStorageAdapter(ABC):
    @abstractmethod
    def upload(self, name: str, content: bytes, *, content_type: str) -> ExternalResult:
        raise NotImplementedError

    @abstractmethod
    def download(self, object_id: str) -> ExternalResult:
        raise NotImplementedError


class CallbackAdapter(ABC):
    @abstractmethod
    def trigger(self, event: str, payload: dict[str, Any], *, correlation_id: str) -> ExternalResult:
        raise NotImplementedError


def adapter_readiness(adapter: Any, required_methods: list[str]) -> dict[str, Any]:
    missing = [method for method in required_methods if not callable(getattr(adapter, method, None))]
    return {"ready": not missing, "missing_methods": missing,
            "verification_level": "external_ready" if not missing else "contract"}
