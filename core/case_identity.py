"""Stable case identity across suite versions and recycled display IDs."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any


def normalize_title(title: str) -> str:
    text = re.sub(r"^TC\d+[\s_:-]*", "", str(title or ""), flags=re.IGNORECASE)
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", text).lower()


def semantic_signature(case: dict[str, Any], *, suite_fingerprint: str = "") -> str:
    source = case.get("source") or {}
    payload = {
        "suite_fingerprint": suite_fingerprint or source.get("suite_fingerprint") or "",
        "title": normalize_title(str(case.get("title") or "")),
        "module": str(case.get("module") or source.get("module") or "").strip().lower(),
        "scenario": str(case.get("scenario_type") or "").strip().lower(),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]


def compatible_identity(
    case: dict[str, Any],
    binding: dict[str, Any],
    *,
    suite_fingerprint: str = "",
) -> tuple[bool, str]:
    expected = semantic_signature(case, suite_fingerprint=suite_fingerprint)
    actual = str(binding.get("semantic_signature") or "")
    if not actual:
        return False, "binding has no semantic_signature"
    if actual != expected:
        return False, "semantic signature mismatch"
    bound_fingerprint = str(binding.get("suite_fingerprint") or "")
    if bound_fingerprint and suite_fingerprint and bound_fingerprint != suite_fingerprint:
        return False, "suite fingerprint mismatch"
    return True, "compatible"
