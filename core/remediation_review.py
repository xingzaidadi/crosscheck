"""Review and safely promote remediation drafts into approved assets."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

SUPPORTED_PROOFS = {"ui_check", "ui", "api_response", "api", "db_assertion", "db", "reconcile", "event", "script"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_plan(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    data = json.loads(target.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("mode") != "review_only":
        raise ValueError("remediation plan must be a review_only plan")
    return data


def _find_draft(plan: dict[str, Any], asset_id: str) -> tuple[str, dict[str, Any]]:
    for asset_type, key in (("fixture", "fixture_drafts"), ("oracle", "oracle_drafts")):
        for draft in plan.get(key, []):
            if draft.get("fixture_id") == asset_id or draft.get("oracle_id") == asset_id:
                return asset_type, draft
    raise ValueError(f"draft asset not found: {asset_id}")


def validate_draft(asset_type: str, draft: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if asset_type == "fixture":
        if draft.get("strategy") in {None, "", "needs_review"}:
            errors.append("fixture.strategy must be selected")
        if not isinstance(draft.get("steps"), list) or not draft.get("steps"):
            errors.append("fixture.steps must contain executable preparation steps")
        cleanup = draft.get("cleanup_contract") or {}
        if not cleanup.get("required") or not cleanup.get("declared"):
            errors.append("fixture.cleanup_contract must be declared")
    elif asset_type == "oracle":
        assertions = draft.get("assertions")
        if not isinstance(assertions, list) or not assertions:
            errors.append("oracle.assertions must contain structured assertions")
        else:
            seen: set[str] = set()
            for index, item in enumerate(assertions):
                if not isinstance(item, dict):
                    errors.append(f"oracle.assertions[{index}] must be an object")
                    continue
                identifier = str(item.get("id") or "")
                if not identifier:
                    errors.append(f"oracle.assertions[{index}].id is required")
                elif identifier in seen:
                    errors.append(f"oracle.assertions[{index}].id is duplicated")
                seen.add(identifier)
                proof = str(item.get("proof") or item.get("kind") or "").lower()
                if proof not in SUPPORTED_PROOFS:
                    errors.append(f"oracle.assertions[{index}].proof is unsupported")
                if "expected" not in item:
                    errors.append(f"oracle.assertions[{index}].expected is required")
    else:
        errors.append(f"unsupported asset type: {asset_type}")
    return errors


def _write_asset(suite_dir: Path, asset_type: str, asset: dict[str, Any]) -> Path:
    root = suite_dir / "approved_assets" / ("fixtures" if asset_type == "fixture" else "oracles")
    root.mkdir(parents=True, exist_ok=True)
    identifier = asset.get("fixture_id") or asset.get("oracle_id")
    safe = "".join(char if char.isalnum() or char in "._-" else "_" for char in str(identifier))
    path = root / f"{safe}.yaml"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(yaml.safe_dump(asset, allow_unicode=True, sort_keys=False), encoding="utf-8")
    temporary.replace(path)
    return path


def review_draft(
    plan_path: str | Path,
    suite_dir: str | Path,
    asset_id: str,
    *,
    reviewer: str,
    decision: str,
    updates: dict[str, Any] | None = None,
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    if not reviewer.strip():
        raise ValueError("reviewer is required")
    if decision not in {"approve", "reject"}:
        raise ValueError("decision must be approve or reject")
    plan_path = Path(plan_path)
    plan = load_plan(plan_path)
    asset_type, draft = _find_draft(plan, asset_id)
    if updates:
        draft.update(updates)
    if decision == "approve":
        errors = validate_draft(asset_type, draft)
        if errors:
            raise ValueError("draft is not approvable: " + "; ".join(errors))
        if asset_type == "fixture":
            draft["verified"] = True
    draft["status"] = "approved" if decision == "approve" else "rejected"
    draft["approved_by"] = reviewer if decision == "approve" else ""
    draft["reviewed_by"] = reviewer
    draft["reviewed_at"] = _now()
    draft["review_evidence"] = list(evidence or [])
    draft["content_hash"] = _hash({key: value for key, value in draft.items()
                                    if key not in {"content_hash", "reviewed_at", "review_evidence"}})
    for task in plan.get("tasks", []):
        if task.get("draft_asset_id") == asset_id:
            task["status"] = "approved" if decision == "approve" else "rejected"
            task["reviewed_by"] = reviewer
            task["reviewed_at"] = draft["reviewed_at"]
    plan.setdefault("review_audit", []).append({
        "asset_id": asset_id, "asset_type": asset_type, "decision": decision,
        "reviewer": reviewer, "at": draft["reviewed_at"], "evidence": list(evidence or []),
    })
    temporary = plan_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(plan_path)
    asset_path = None
    if decision == "approve":
        asset_path = _write_asset(Path(suite_dir), asset_type, draft)
    return {"asset_type": asset_type, "asset_id": asset_id, "decision": decision,
            "reviewer": reviewer, "plan": str(plan_path),
            "approved_asset": str(asset_path) if asset_path else None,
            "content_hash": draft["content_hash"]}
