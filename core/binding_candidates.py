"""Generate reviewable execution bindings from observed assets.

Candidates never become executable automatically.  They retain source hashes,
confidence and unresolved placeholders so a reviewer can approve exact facts.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from core.case_identity import semantic_signature


_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{2,}", value.lower()))


def _source_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def rank_observations(case: dict[str, Any], observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions = case.get("actions") or {}
    assertions = case.get("assertions") or {}
    data = case.get("data") or {}
    raw_query = " ".join(str(value or "") for value in (
        case.get("title"), case.get("module"), case.get("steps"), case.get("expected"),
        case.get("notes"), actions.get("source_text") if isinstance(actions, dict) else actions,
        assertions.get("source_text") if isinstance(assertions, dict) else assertions,
        data.get("preconditions_text") if isinstance(data, dict) else data,
    ))
    query = _tokens(raw_query)
    ranked = []
    for observation in observations:
        method = str(observation.get("method") or "").upper()
        path = str(observation.get("path") or observation.get("url") or "")
        body = observation.get("body") or observation.get("request_body") or {}
        haystack = _tokens(f"{method} {path} {json.dumps(body, ensure_ascii=False, default=str)}")
        overlap = len(query & haystack)
        exact_path = bool(path and path in raw_query)
        score = min(0.99, 0.25 + overlap * 0.12 + (0.15 if method in _METHODS else 0)
                    + (0.5 if exact_path else 0))
        ranked.append({"observation": observation, "confidence": round(score, 2), "overlap": overlap})
    return sorted(ranked, key=lambda item: (-item["confidence"], -item["overlap"]))


def generate_binding_candidate(
    case: dict[str, Any],
    observations: list[dict[str, Any]],
    *,
    suite_fingerprint: str,
    minimum_confidence: float = 0.5,
) -> dict[str, Any]:
    ranked = rank_observations(case, observations)
    selected = ranked[0] if ranked else None
    unresolved = []
    execution: dict[str, Any] = {}
    if selected and selected["confidence"] >= minimum_confidence:
        observed = selected["observation"]
        execution = {
            "mode": "api",
            "request": {
                "method": str(observed.get("method") or "GET").upper(),
                "url": str(observed.get("path") or observed.get("url") or ""),
                "body": observed.get("body") or observed.get("request_body"),
            },
        }
        if execution["request"]["body"] is None and execution["request"]["method"] not in {"GET", "DELETE"}:
            unresolved.append("request.body")
    else:
        unresolved.append("execution.request")
    return {
        "case_id": str(case.get("case_id") or ""),
        "semantic_signature": semantic_signature(case, suite_fingerprint=suite_fingerprint),
        "suite_fingerprint": suite_fingerprint,
        "state": "candidate",
        "confidence": selected["confidence"] if selected else 0,
        "execution": execution,
        "unresolved": unresolved,
        "source_hashes": [_source_hash(item["observation"]) for item in ranked[:3]],
        "ranked_sources": ranked[:3],
    }


def candidate_executable(candidate: dict[str, Any]) -> bool:
    return candidate.get("state") == "approved" and not candidate.get("unresolved") \
        and float(candidate.get("confidence") or 0) >= 0.5
