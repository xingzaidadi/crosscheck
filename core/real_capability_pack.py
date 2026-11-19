"""Declarative bindings for real-system capability packs.

Bindings deliberately contain no credentials.  A profile supplies the site,
session and base URL; this module only turns approved endpoint declarations
into executable handlers.  Missing bindings remain visible as validation
errors instead of being silently replaced by a mock.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from core.business_capabilities import CapabilityPack


@dataclass(frozen=True)
class RealBinding:
    capability: str
    method: str
    path: str
    layer: str = "api"
    mutates: bool = False
    idempotent: bool = False
    evidence: tuple[str, ...] = ()
    compensate_with: str | None = None

    def contract_errors(self) -> list[str]:
        errors: list[str] = []
        if not self.capability.strip():
            errors.append("capability is required")
        if self.method.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            errors.append(f"unsupported method: {self.method}")
        if not self.path.startswith("/"):
            errors.append(f"path must start with '/': {self.path}")
        if self.mutates and not self.idempotent:
            errors.append(f"mutating capability is not idempotent: {self.capability}")
        if self.mutates and not self.compensate_with:
            errors.append(f"mutating capability has no compensation: {self.capability}")
        return errors


def build_real_pack(
    name: str,
    version: str,
    bindings: list[RealBinding],
    *,
    request: Callable[[str, str, dict[str, Any]], dict[str, Any]],
    compensate: Callable[[str, str, dict[str, Any]], dict[str, Any]] | None = None,
) -> CapabilityPack:
    """Build a pack whose handlers delegate to a supplied authenticated client."""
    pack = CapabilityPack(name, version)
    for binding in bindings:
        errors = binding.contract_errors()
        if errors:
            raise ValueError(f"{binding.capability}: {'; '.join(errors)}")

        def handler(*, inputs: dict[str, Any], context: dict[str, Any], _binding=binding):
            return request(_binding.method.upper(), _binding.path, {
                "inputs": inputs,
                "context": context,
            })

        compensator = None
        if binding.compensate_with and compensate is not None:
            def compensator(*, inputs: dict[str, Any], context: dict[str, Any], _binding=binding):
                return compensate(_binding.compensate_with or "", _binding.path, {
                    "inputs": inputs,
                    "context": context,
                })

        pack.register(binding.capability, handler, compensator=compensator,
                      evidence=list(binding.evidence))
    return pack

