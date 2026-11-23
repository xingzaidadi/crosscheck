"""Generate reviewable remediation tasks for blocked business test cases.

The generator is intentionally non-mutating: it creates draft assets and task
records, but never promotes them into executable configuration.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from .oracle_readiness import assess_case_oracles
from .precondition_readiness import assess_case_preconditions


def _slug(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in value)[:100]


def _id(prefix: str, *values: Any) -> str:
    raw = "|".join(str(value) for value in values)
    return f"{prefix}:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]}"


def _case_text(case: dict[str, Any]) -> str:
    data = case.get("data") or {}
    if not isinstance(data, dict):
        data = {}
    values = [case.get("preconditions"), data.get("preconditions_text"), case.get("notes")]
    return " ".join(str(value) for value in values if value not in (None, "", [], {})).strip()


def _required_evidence(case: dict[str, Any]) -> list[str]:
    evidence = case.get("evidence") or {}
    values = evidence.get("required") if isinstance(evidence, dict) else evidence
    return [str(value) for value in (values if isinstance(values, list) else [values]) if value]


def _fixture_draft(case: dict[str, Any], precondition: dict[str, Any]) -> dict[str, Any]:
    case_id = str(case.get("case_id") or "")
    case_key = str((case.get("source") or {}).get("case_key") or case_id)
    cleanup = case.get("cleanup") or {}
    return {
        "schema_version": 1,
        "fixture_id": _id("fixture", case_id),
        "name": f"fixture_{_slug(case_key)}",
        "verified": False,
        "case_keys": [case_key],
        "source_condition": _case_text(case),
        "strategy": "needs_review",
        "strategy_candidates": ["api_workflow", "database_seed", "state_transition", "manual"],
        "steps": [],
        "cleanup_contract": {
            "required": True,
            "declared": bool(cleanup),
            "review_required": True,
        },
        "review": {
            "status": "pending",
            "required_fields": ["strategy", "steps", "cleanup_contract"],
            "reason": precondition["reason"],
        },
    }


def _oracle_draft(case: dict[str, Any], oracle: dict[str, Any]) -> dict[str, Any]:
    case_id = str(case.get("case_id") or "")
    required = _required_evidence(case)
    return {
        "schema_version": 1,
        "oracle_id": _id("oracle", case_id),
        "case_id": case_id,
        "status": "draft",
        "proof_candidates": required,
        "assertions": [],
        "source_expectation": (case.get("assertions") or {}).get("source_text", "")
        if isinstance(case.get("assertions"), dict) else "",
        "missing_evidence": oracle["missing_evidence"],
        "review": {
            "status": "pending",
            "human_confirmation_required": True,
            "required_fields": ["assertions", "proof", "expected"],
            "reason": oracle["reason"],
        },
    }


def generate_remediation_plan(
    cases: list[dict[str, Any]],
    *,
    suite_dir: str | Path | None = None,
    workspace: str | Path | None = None,
) -> dict[str, Any]:
    """Create non-mutating tasks and draft assets for a suite."""
    tasks: list[dict[str, Any]] = []
    fixture_drafts: list[dict[str, Any]] = []
    oracle_drafts: list[dict[str, Any]] = []
    for case in cases:
        precondition = assess_case_preconditions(case, suite_dir=suite_dir, workspace=workspace)
        oracle = assess_case_oracles(case)
        case_id = str(case.get("case_id") or "")
        priority = str(case.get("priority") or "P2")
        if precondition["status"] == "blocked":
            fixture = _fixture_draft(case, precondition)
            fixture_drafts.append(fixture)
            tasks.append({
                "task_id": _id("task", case_id, "state"),
                "case_id": case_id,
                "type": "state_recipe",
                "category": "state_blocked",
                "priority": priority,
                "status": "draft",
                "title": "补充前置状态准备能力",
                "reason": precondition["reason"],
                "draft_asset_id": fixture["fixture_id"],
                "next_action": "确认数据来源、状态推进步骤、环境和清理/补偿策略",
                "human_confirmation_required": True,
            })
        if oracle["status"] != "ready":
            draft = _oracle_draft(case, oracle)
            oracle_drafts.append(draft)
            tasks.append({
                "task_id": _id("task", case_id, "oracle"),
                "case_id": case_id,
                "type": "business_oracle",
                "category": "oracle_blocked" if oracle["status"] == "blocked" else "oracle_partial",
                "priority": priority,
                "status": "draft",
                "title": "补充结构化业务 Oracle",
                "reason": oracle["reason"],
                "draft_asset_id": draft["oracle_id"],
                "next_action": "确认预期值、断言操作符和可复核的 UI/API/DB/Event/Log 证据来源",
                "human_confirmation_required": True,
            })
    return {
        "schema_version": 1,
        "mode": "review_only",
        "total_cases": len(cases),
        "task_count": len(tasks),
        "tasks": tasks,
        "fixture_drafts": fixture_drafts,
        "oracle_drafts": oracle_drafts,
        "approval_policy": "draft assets never become executable without named human review",
    }


def write_remediation_plan(plan: dict[str, Any], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_draft_assets(plan: dict[str, Any], directory: str | Path) -> list[Path]:
    root = Path(directory)
    fixtures = root / "fixtures"
    oracles = root / "oracles"
    fixtures.mkdir(parents=True, exist_ok=True)
    oracles.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for draft in plan["fixture_drafts"]:
        path = fixtures / f"{_slug(draft['fixture_id'])}.yaml"
        path.write_text(yaml.safe_dump(draft, allow_unicode=True, sort_keys=False), encoding="utf-8")
        paths.append(path)
    for draft in plan["oracle_drafts"]:
        path = oracles / f"{_slug(draft['oracle_id'])}.yaml"
        path.write_text(yaml.safe_dump(draft, allow_unicode=True, sort_keys=False), encoding="utf-8")
        paths.append(path)
    return paths
