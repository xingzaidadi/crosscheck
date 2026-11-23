"""Aggregate consecutive suite runs into a soak stability report.

This turns many independent run summary.json files into one soak result with
per-case pass rates, overall stability, aggregated asset usage, and a
soak_runs count that the quality gate and asset-health evaluators consume.
It never fabricates runs: only real summary.json files on disk are counted.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


PASS = {"pass", "passed"}
INCONCLUSIVE = {"partial", "unknown", "inconclusive"}
BLOCKED = {"skip", "blocked", "invalid_spec", "env_error"}


def _load(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _classify(verdict: str) -> str:
    value = str(verdict or "").lower()
    if value in PASS:
        return "pass"
    if value in INCONCLUSIVE:
        return "inconclusive"
    if value in BLOCKED:
        return "blocked"
    return "fail"


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def aggregate_soak(runs_root: str | Path, *, min_runs: int = 5) -> dict[str, Any]:
    """Aggregate every summary.json under runs_root in chronological order."""
    root = Path(runs_root)
    summaries = sorted(root.glob("*/summary.json"),
                       key=lambda path: path.stat().st_mtime if path.exists() else 0)
    runs: list[dict[str, Any]] = []
    per_case: dict[str, dict[str, Any]] = {}
    asset_usage: dict[str, dict[str, Any]] = {}
    for summary_path in summaries:
        summary = _load(summary_path)
        if not summary:
            continue
        run_id = str(summary.get("run_id") or summary_path.parent.name)
        cases = summary.get("cases") or []
        run_pass = run_fail = run_inconclusive = run_blocked = 0
        for case in cases:
            if not isinstance(case, dict):
                continue
            case_id = str(case.get("case_id") or "")
            outcome = _classify(case.get("verdict"))
            bucket = per_case.setdefault(case_id, {"case_id": case_id, "runs": 0, "passes": 0,
                                                   "failures": 0, "inconclusive": 0, "blocked": 0})
            bucket["runs"] += 1
            if outcome == "pass":
                bucket["passes"] += 1
                run_pass += 1
            elif outcome == "inconclusive":
                bucket["inconclusive"] += 1
                run_inconclusive += 1
            elif outcome == "blocked":
                bucket["blocked"] += 1
                run_blocked += 1
            else:
                bucket["failures"] += 1
                run_fail += 1
            usage = case.get("asset_usage") or {}
            for kind in ("fixture", "oracle"):
                item = usage.get(kind) or {}
                if isinstance(item, dict) and item.get("asset_id"):
                    key = kind + ":" + str(item["asset_id"])
                    stats = asset_usage.setdefault(key, {"asset_type": kind, "asset_id": item["asset_id"],
                                                         "runs": 0, "passes": 0})
                    stats["runs"] += 1
                    if outcome == "pass":
                        stats["passes"] += 1
        run_total = len(cases)
        runs.append({"run_id": run_id, "total": run_total, "pass": run_pass, "fail": run_fail,
                     "inconclusive": run_inconclusive, "blocked": run_blocked,
                     "passed": run_total > 0 and run_pass == run_total})

    soak_runs = len(runs)
    passed_runs = sum(run["passed"] for run in runs)
    for bucket in per_case.values():
        bucket["pass_rate"] = _ratio(bucket["passes"], bucket["runs"])
    for stats in asset_usage.values():
        stats["pass_rate"] = _ratio(stats["passes"], stats["runs"])
    stability = _ratio(passed_runs, soak_runs)
    return {
        "schema_version": 1,
        "runs_root": str(root),
        "soak_runs": soak_runs,
        "passed_runs": passed_runs,
        "stability": stability,
        "min_runs": min_runs,
        "meets_min_runs": soak_runs >= min_runs,
        "all_runs_passed": soak_runs > 0 and passed_runs == soak_runs,
        "runs": runs,
        "per_case": sorted(per_case.values(), key=lambda item: item["pass_rate"]),
        "asset_usage": sorted(asset_usage.values(), key=lambda item: item["pass_rate"]),
    }


def build_soak_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Build a quality-gate-consumable summary.json from a soak report."""
    total = sum(run["total"] for run in report["runs"])
    passed = sum(run["pass"] for run in report["runs"])
    inconclusive = sum(run["inconclusive"] for run in report["runs"])
    cases = [{"case_id": item["case_id"],
              "verdict": "PASS" if item["pass_rate"] >= 1.0 else "FAIL",
              "pass_rate": item["pass_rate"]} for item in report["per_case"]]
    return {
        "run_id": "soak-aggregate",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "soak_runs": report["soak_runs"],
        "total": total,
        "pass": passed,
        "passed": passed,
        "inconclusive": inconclusive,
        "stability": report["stability"],
        "cases": cases,
    }


def write_soak(report: dict[str, Any], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
