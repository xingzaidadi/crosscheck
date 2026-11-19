"""Audit UI readiness, candidate assets and external evidence in one report."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from core.ui_readiness import gap_rows, summarize_ui_readiness
from core.ui_task_queue import build_task_queue, queue_summary


def audit(workspace: str | Path, readiness: str | Path | None = None) -> dict:
    root = Path(workspace).resolve()
    readiness_path = Path(readiness).resolve() if readiness else None
    if readiness_path is None:
        matches = sorted((root / "suites").glob("*/reports/ui_first_readiness.json"), key=lambda p: p.stat().st_mtime)
        readiness_path = matches[-1] if matches else None
    report = json.loads(readiness_path.read_text(encoding="utf-8")) if readiness_path and readiness_path.is_file() else {"cases": []}
    freshness = {"fresh": False, "age_seconds": None, "warning": "readiness report not found"}
    if readiness_path and readiness_path.is_file():
        age = max(0, time.time() - readiness_path.stat().st_mtime)
        freshness = {"fresh": age <= 24 * 3600, "age_seconds": round(age),
                     "warning": "" if age <= 24 * 3600 else "readiness report is older than 24 hours"}
    candidates = []
    candidate_dir = root / "knowledge_base" / "asset_candidates"
    for path in sorted(candidate_dir.glob("*.json")) if candidate_dir.is_dir() else []:
        try:
            candidates.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    states = {}
    for item in candidates:
        state = str(item.get("state") or "unknown")
        states[state] = states.get(state, 0) + 1
    readiness_summary = summarize_ui_readiness(report)
    tasks = build_task_queue(report)
    return {
        "schema_version": 1,
        "workspace": str(root),
        "readiness_file": str(readiness_path) if readiness_path else "",
        "readiness": readiness_summary,
        "freshness": freshness,
        "gaps": gap_rows(report),
        "candidate_assets": {"total": len(candidates), "states": states},
        "task_queue": {"summary": queue_summary(tasks), "tasks": tasks},
        "next_actions": [
            "resolve UI_BLOCKED business questions",
            "explore and replay UI_BINDING_REQUIRED cases",
            "human-verify replay evidence before formal PASS",
            "run external acceptance with three unrelated real systems",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--readiness")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = audit(args.workspace, args.readiness)
    output = Path(args.output) if args.output else Path(args.workspace) / "reports" / "ui_gap_audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["readiness"]["ready"] and result["freshness"]["fresh"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
