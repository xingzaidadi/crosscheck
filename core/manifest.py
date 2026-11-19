"""Frozen acceptance manifest identity and integrity checks."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), default=str).encode()).hexdigest()


def freeze_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    frozen = json.loads(json.dumps(manifest, ensure_ascii=False))
    frozen.pop("manifest_hash", None)
    frozen["manifest_hash"] = canonical_hash(frozen)
    return frozen


def verify_manifest(manifest: dict[str, Any]) -> list[str]:
    errors = []
    expected = manifest.get("manifest_hash")
    if not expected:
        errors.append("manifest_hash is required")
    else:
        candidate = dict(manifest)
        candidate.pop("manifest_hash", None)
        if expected != canonical_hash(candidate):
            errors.append("manifest_hash mismatch")
    if not manifest.get("feature_id"):
        errors.append("feature_id is required")
    if not isinstance(manifest.get("required_cases"), list) or not manifest["required_cases"]:
        errors.append("required_cases must be a non-empty list")
    return errors
