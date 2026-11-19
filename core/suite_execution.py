"""Unify canonical cases and reviewed execution bindings into one suite plan."""
from __future__ import annotations

import json
import re
from datetime import datetime
from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.spec import ExecSpec, load_spec
from core.suite_compiler import compile_suite, plan_hash
from core.fixture_registry import fixture_for_case, load_registry, registry_summary


_PAGE_ENTRY = re.compile(r"页面|页签|按钮|展示|显示|输入|点击|切换|弹窗|前端|浏览器")
_FIXTURE = re.compile(r"存在|准备|构造|分别|各状态|前置|已关联|剩余|当前处理人|权限|角色")


def source_case_key(case: dict[str, Any]) -> str:
    return str((case.get("source") or {}).get("case_key") or "").strip()


def canonical_assertion_requirements(case: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    assertions = case.get("assertions") or {}
    identifiers: list[str] = []
    texts: dict[str, str] = {}
    for layer, items in assertions.items():
        if layer == "source_text" or not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            assertion_id = str(item["id"])
            identifiers.append(assertion_id)
            texts[assertion_id] = str(item.get("expected") or item.get("description") or "")
    if identifiers:
        return identifiers, texts
    source_text = str(assertions.get("source_text") or "")
    lines = []
    for line in source_text.splitlines():
        normalized = re.sub(r"^\s*(?:\d+[.、)]|[-*])\s*", "", line).strip()
        if normalized:
            lines.append(normalized)
    key = source_case_key(case) or str(case.get("case_id") or "case")
    for index, text in enumerate(lines, start=1):
        assertion_id = f"{key}:expected:{index}"
        identifiers.append(assertion_id)
        texts[assertion_id] = text
    return identifiers, texts


def binding_case_key(path: Path, spec: ExecSpec) -> str:
    explicit = str((spec.raw or {}).get("canonical_case_key") or "").strip()
    if explicit:
        return explicit
    filename_key = path.stem.strip()
    if filename_key:
        return filename_key
    return str(spec.case_id).split("-UI", 1)[0].strip()


def provided_layers(spec: ExecSpec) -> list[str]:
    layers: list[str] = []
    if spec.mode == "ui" or spec.ui:
        layers.append("ui")
    if spec.mode in {"api", "write", "reconcile"} or spec.request or (spec.ui or {}).get("url_pattern"):
        layers.append("api")
    if spec.mode == "reconcile" or (spec.assertions or {}).get("db") or (
        spec.mode == "ui" and spec.db and spec.feature
    ):
        layers.append("db")
    if spec.mode == "script":
        layers.append("script")
    return list(dict.fromkeys(layers))


def readiness_gaps(case: dict[str, Any], spec: ExecSpec | None) -> list[str]:
    gaps: list[str] = []
    required = set((case.get("layers") or {}).get("required") or [])
    source_text = "\n".join(str(value or "") for value in (
        (case.get("data") or {}).get("preconditions_text"),
        (case.get("actions") or {}).get("source_text"),
        (case.get("assertions") or {}).get("source_text"),
    ))
    execution = case.get("execution") or {}
    if not spec:
        if "ui" in required or _PAGE_ENTRY.search(source_text):
            gaps.extend(["page_entry", "semantic_actions", "ui_oracle", "replay"])
        if "api" in required:
            gaps.append("api_binding")
        if "db" in required:
            gaps.append("db_oracle")
        if _FIXTURE.search(str((case.get("data") or {}).get("preconditions_text") or "")):
            gaps.append("fixture_recipe")
        if not (case.get("approval") or {}).get("content_hash"):
            gaps.append("spec_approval")
    else:
        if (spec.mode == "ui" or "ui" in required) and not (spec.ui or {}).get("page_url"):
            gaps.append("page_entry")
        if (spec.mode == "ui" or "ui" in required) and not (spec.ui or {}).get("actions"):
            gaps.append("semantic_actions")
        if "ui" in required and not any((spec.ui or {}).get(key) for key in (
            "extract", "visibility_asserts", "value_asserts", "field_asserts", "expect_validation",
        )):
            gaps.append("ui_oracle")
        # A binding is not executable merely because it has an oracle-shaped
        # field. Every canonical expectation must have a concrete proof.
        required_ids, _ = canonical_assertion_requirements(case)
        if (spec.mode == "ui" or "ui" in required) and not required_ids:
            gaps.append("assertion_coverage")
        bindings = (spec.raw or {}).get("assertion_bindings") or {}
        explicit_coverage = required_ids and all(
            isinstance(bindings.get(item), dict)
            and bindings[item].get("proof")
            and bindings[item].get("ref")
            for item in required_ids
        )
        ui = spec.ui or {}
        concrete_ui_oracles = sum(
            len(ui.get(name) or [])
            for name in ("visibility_asserts", "value_asserts", "field_asserts", "expect_validation")
        )
        ordered_ui_coverage = bool(required_ids) and concrete_ui_oracles >= len(required_ids)
        if required_ids and not explicit_coverage and not ordered_ui_coverage:
            gaps.append("assertion_coverage")
        if "api" in required and not (spec.request or (spec.ui or {}).get("url_pattern")):
            gaps.append("api_binding")
        if "db" in required and not (spec.mapping or (spec.assertions or {}).get("db") or (spec.db and spec.feature)):
            gaps.append("db_oracle")
        if _FIXTURE.search(str((case.get("data") or {}).get("preconditions_text") or "")) and not (
            spec.data_prep or spec.prepare_state
        ):
            gaps.append("fixture_recipe")
    if execution.get("blocked") or case.get("status") == "blocked":
        gaps.append("business_rule")
    return list(dict.fromkeys(gaps))


def _latest_replay_status(suite_dir: Path, case_key: str) -> tuple[str, str]:
    """Read the latest recorded UI run as replay evidence, never as business PASS."""
    runs = suite_dir / "reports" / "runs"
    latest: tuple[float, str, str] | None = None
    if not runs.is_dir():
        return "missing", ""
    for summary in runs.glob("*/summary.json"):
        try:
            data = json.loads(summary.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for item in data.get("cases") or []:
            if str(item.get("case_id") or "") not in {case_key, case_key.split("/")[-1]}:
                continue
            phase = str(item.get("phase_verdict") or "")
            if phase not in {"UI_PASS", "UI_FAIL", "UI_INCONCLUSIVE"}:
                continue
            timestamp = summary.stat().st_mtime
            if latest is None or timestamp > latest[0]:
                latest = (timestamp, "replay_verified" if phase == "UI_PASS" else "replay_failed", str(summary))
    return (latest[1], latest[2]) if latest else ("missing", "")


def assertion_candidates(case: dict[str, Any], spec: ExecSpec | None) -> list[dict[str, Any]]:
    """Expose unresolved expectation bindings as reviewable, non-executable candidates."""
    if not spec:
        return []
    knowledge = (spec.raw or {}).get("assertion_knowledge") or {}
    candidates = []
    from core.exploration_plan import build_exploration_task
    for item in knowledge.get("candidates") or []:
        candidates.append(build_exploration_task({
            "case_id": case.get("case_id"),
            "source_case_key": source_case_key(case),
            "assertion_id": item.get("assertion_id"),
            "text": item.get("text", ""),
            "state": "candidate",
            "required_review": ["proof_type", "proof_ref", "replay"],
            "suggested_assets": [
                "approved page model",
                "approved action asset",
                "approved query mapping",
            ],
        }, page_url=str((getattr(spec, "ui", {}) or {}).get("page_url") or ""),
        session=str(getattr(spec, "session", "") or "")))
    return candidates


def ui_candidate(case: dict[str, Any], spec: ExecSpec | None) -> dict[str, Any] | None:
    required = set((case.get("layers") or {}).get("required") or [])
    if "ui" not in required or (spec and "ui" in provided_layers(spec)):
        return None
    actions = str((case.get("actions") or {}).get("source_text") or "")
    assertions = str((case.get("assertions") or {}).get("source_text") or "")
    labels = list(dict.fromkeys(re.findall(r"【([^】]+)】", actions + "\n" + assertions)))
    return {
        "source_case_key": source_case_key(case),
        "title": case.get("title"),
        "priority": case.get("priority"),
        "candidate": {
            "mode": "ui",
            "page_entry": "REVIEW_REQUIRED",
            "semantic_actions": actions,
            "oracle_text": assertions,
            "control_labels": labels,
        },
        "required_review": ["page_entry", "semantic_actions", "ui_oracle", "replay"],
    }


def load_reviewed_bindings(suite_dir: Path, cases: list[dict[str, Any]]) -> tuple[dict[str, ExecSpec], list[dict]]:
    canonical = {source_case_key(case): case for case in cases if source_case_key(case)}
    selected: dict[str, ExecSpec] = {}
    invalid: list[dict] = []
    # UI bindings are the current reviewed source for UI-first execution.
    # Prefer them over legacy bindings when both contain the same case key.
    binding_dirs = [suite_dir / "ui_bindings", suite_dir / "bindings"]
    for directory in binding_dirs:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.yaml")):
            try:
                spec = load_spec(path)
                key = binding_case_key(path, spec)
                if key not in canonical:
                    raise ValueError(f"binding has no canonical source case: {key}")
                if spec.verify_status != "human_verified":
                    raise ValueError("binding is not human_verified")
                if key in selected:
                    continue
                spec.case_id = key
                spec.raw = {
                    **(spec.raw or {}),
                    "canonical_case_id": canonical[key]["case_id"],
                    "canonical_case_key": key,
                    "binding_path": str(path),
                    "execution_source": "reviewed_binding",
                }
                required_ids, assertion_texts = canonical_assertion_requirements(canonical[key])
                if required_ids and not (spec.raw or {}).get("assertion_ids"):
                    spec.raw["assertion_ids"] = required_ids
                    spec.raw["assertion_texts"] = assertion_texts
                    from core.assertion_knowledge import match_assertion_knowledge
                    matched = match_assertion_knowledge(
                        canonical[key], spec, suite_dir.parent.parent, assertion_texts
                    )
                    spec.raw["assertion_bindings"] = matched["bindings"]
                    spec.raw["assertion_knowledge"] = matched
                    if matched["dependencies"]:
                        spec.raw["knowledge_dependencies"] = matched["dependencies"]
                selected[key] = spec
            except Exception as exc:  # noqa: BLE001
                invalid.append({"case_id": path.stem, "source": str(path), "error": str(exc)})
    return selected, invalid


def build_execution_plan(
    suite: dict[str, Any], cases: list[dict[str, Any]], context, suite_dir: Path,
    *, phase: str = "all",
) -> tuple[list[ExecSpec], dict[str, Any]]:
    canonical_specs, canonical_invalid = compile_suite(suite, cases, context)
    fixture_registry = load_registry(suite_dir)
    reviewed, binding_invalid = load_reviewed_bindings(suite_dir, cases)
    canonical_by_key = {
        str((spec.raw or {}).get("canonical_case_key") or ""): spec
        for spec in canonical_specs
    }
    selected: list[ExecSpec] = []
    rows: list[dict[str, Any]] = []
    invalid_by_case = {
        str(item.get("case_id") or ""): item for item in canonical_invalid + binding_invalid
    }
    for case in cases:
        key = source_case_key(case)
        spec = canonical_by_key.get(key) or reviewed.get(key)
        required = list((case.get("layers") or {}).get("required") or [])
        provided = provided_layers(spec) if spec else []
        missing = [layer for layer in required if layer not in provided]
        gaps = readiness_gaps(case, spec)
        fixture = fixture_for_case(fixture_registry, key)
        if fixture:
            gaps = [gap for gap in gaps if gap != "fixture_recipe"]
            if spec and not spec.data_prep and fixture.get("steps"):
                spec.data_prep = list(fixture.get("steps") or [])
                spec.raw["fixture_name"] = fixture.get("name")
                spec.raw["fixture_source"] = fixture.get("source")
        blocked_reason = str((spec.blocked if spec else "") or (case.get("execution") or {}).get("blocked") or "")
        if phase == "ui" and spec and (spec.mode == "ui" or spec.ui):
            gaps = [gap for gap in gaps if gap not in {
                "api_binding", "db_oracle", "fixture_recipe", "business_rule",
                "replay_required",
            }]
            blocked_reason = ""
            spec.blocked = ""
        binding_health = str((spec.raw or {}).get("binding_health") or "") if spec else ""
        cross_layer_health = {"db_oracle_incomplete", "api_oracle_incomplete", "cross_layer_incomplete"}
        if binding_health and binding_health != "verified" and not (
            phase == "ui" and binding_health in cross_layer_health
        ):
            blocked_reason = blocked_reason or f"binding health: {binding_health}"
        replay_status, replay_source = _latest_replay_status(suite_dir, key)
        # Keep replay visible as a diagnostic gap, while the UI phase above
        # explicitly treats it as non-blocking for a fresh run.
        if spec and (spec.mode == "ui" or spec.ui) and replay_status != "replay_verified":
            gaps.append("replay_required")
            if phase == "ui":
                gaps.remove("replay_required")
        if spec and replay_source:
            spec.raw["replay_status"] = replay_status
            spec.raw["replay_evidence"] = replay_source
        blocked = case.get("status") == "blocked" or bool(blocked_reason)
        invalid = invalid_by_case.get(str(case.get("case_id") or "")) or invalid_by_case.get(key)
        if invalid:
            state = "INVALID"
            reason = invalid["error"]
        elif blocked:
            state = "BLOCKED"
            reason = blocked_reason or "canonical case is blocked"
        elif spec and not gaps:
            state = "EXECUTION_READY"
            reason = str((spec.raw or {}).get("execution_source") or "approved_canonical")
            selected.append(spec)
        elif spec:
            if "assertion_coverage" in gaps or "ui_oracle" in gaps:
                state = "ASSERTION_REQUIRED"
                reason = "one or more business expectations lack executable proof"
            elif "fixture_recipe" in gaps:
                state = "FIXTURE_REQUIRED"
                reason = "required test data has no verified fixture recipe"
            elif "replay_required" in gaps:
                state = "REPLAY_REQUIRED"
                reason = "latest UI replay is missing or did not pass"
            else:
                state = "BLOCKED"
                reason = "binding does not satisfy execution readiness gates"
        else:
            state = "BINDING_REQUIRED"
            reason = "no approved canonical execution or reviewed binding"
        rows.append({
            "case_id": case.get("case_id"),
            "source_case_key": key,
            "title": case.get("title"),
            "priority": case.get("priority"),
            "canonical_status": case.get("status"),
            "spec_verified": bool(spec and spec.verify_status == "human_verified"),
            "execution_ready": state == "EXECUTION_READY",
            "full_coverage_ready": state == "EXECUTION_READY" and not missing,
            "execution_source": reason if state == "EXECUTION_READY" else "",
            "required_layers": required,
            "provided_layers": provided,
            "missing_layers": missing,
            "readiness_gaps": gaps,
            "fixture": fixture.get("name") if fixture else "",
            "state": state,
            "reason": reason,
            "assertion_candidates": assertion_candidates(case, spec),
            "replay_status": replay_status if spec else "missing",
            "replay_evidence": replay_source,
        })
    counts: dict[str, int] = {}
    gap_counts: dict[str, int] = {}
    for row in rows:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
        for gap in row["readiness_gaps"]:
            gap_counts[gap] = gap_counts.get(gap, 0) + 1
    report = {
        "suite_id": suite.get("suite_id"),
        "phase": phase,
        "total": len(rows),
        "execution_ready": len(selected),
        "execution_ready_rate": round(len(selected) / len(rows) * 100, 1) if rows else 0.0,
        "full_coverage_ready": sum(bool(row["full_coverage_ready"]) for row in rows),
        "p0_total": sum(row["priority"] == "P0" for row in rows),
        "p0_execution_ready": sum(row["priority"] == "P0" and row["execution_ready"] for row in rows),
        "counts": counts,
        "gap_counts": gap_counts,
        "fixture_registry": registry_summary(fixture_registry),
        "invalid": canonical_invalid + binding_invalid,
        "cases": rows,
        "ui_candidates": [candidate for case in cases
                          if (candidate := ui_candidate(case, reviewed.get(source_case_key(case)))) is not None],
        "assertion_candidates": [candidate for row in rows for candidate in row["assertion_candidates"]],
    }
    return selected, report


def write_execution_plan(specs: list[ExecSpec], lifecycle: dict[str, Any], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "plan_hash": plan_hash(specs),
        "lifecycle": lifecycle,
        "specs": [asdict(spec) for spec in specs],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_lifecycle_report(report: dict[str, Any], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = path.with_suffix(".md")
    lines = [
        "# Suite Execution Lifecycle", "",
        f"- Total: {report['total']}",
        f"- Execution ready: {report['execution_ready']}",
        f"- States: {report['counts']}", "",
        f"- Gaps: {report['gap_counts']}", "",
        "|Case|Priority|State|Required|Provided|Reason|",
        "|---|---|---|---|---|---|",
    ]
    for row in report["cases"]:
        lines.append(
            f"|{row['source_case_key']}|{row['priority']}|{row['state']}|"
            f"{','.join(row['required_layers'])}|{','.join(row['provided_layers'])}|{row['reason']}|"
        )
    markdown.write_text("\n".join(lines), encoding="utf-8")
    candidates = path.with_name("ui_binding_candidates.json")
    candidates.write_text(json.dumps({
        "total": len(report.get("ui_candidates") or []),
        "cases": report.get("ui_candidates") or [],
        "assertion_candidates": report.get("assertion_candidates") or [],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
