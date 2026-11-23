"""Aggregate execution outcomes into approved-asset health reports."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml


def _load_summary(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _asset_refs(usage: dict[str, Any]) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for kind in ("fixture", "oracle"):
        item = usage.get(kind) or {}
        if isinstance(item, dict) and item.get("asset_id"):
            refs.append((kind, str(item["asset_id"])))
    return refs


def _status(verdict: str) -> str:
    value = str(verdict or "").lower()
    if value in {"pass", "passed"}:
        return "pass"
    if value in {"partial", "unknown", "inconclusive"}:
        return "inconclusive"
    if value in {"skip", "blocked", "invalid_spec", "env_error"}:
        return "blocked"
    return "fail"


def _health(stats: dict[str, Any], *, degrade_after: int, unhealthy_after: int) -> str:
    total = int(stats["runs"])
    if total == 0:
        return "insufficient_data"
    if int(stats["consecutive_failures"]) >= unhealthy_after:
        return "unhealthy"
    if int(stats["consecutive_failures"]) >= degrade_after or float(stats["success_rate"]) < 0.95:
        return "degraded"
    return "healthy"


def _new_stats(asset_type: str, asset_id: str) -> dict[str, Any]:
    return {
        "asset_type": asset_type, "asset_id": asset_id, "runs": 0, "passes": 0,
        "failures": 0, "inconclusive": 0, "blocked": 0, "cleanup_failures": 0,
        "consecutive_failures": 0, "max_consecutive_failures": 0,
        "failure_classes": {}, "run_ids": [], "cases": [],
    }


def aggregate_asset_health(
    runs_root: str | Path,
    *,
    degrade_after: int = 2,
    unhealthy_after: int = 3,
) -> dict[str, Any]:
    """Aggregate all `summary.json` files under a suite's runs directory."""
    root = Path(runs_root)
    assets: dict[tuple[str, str], dict[str, Any]] = {}
    summaries = sorted(root.glob("*/summary.json"), key=lambda path: path.stat().st_mtime if path.exists() else 0)
    for summary_path in summaries:
        summary = _load_summary(summary_path)
        if not summary:
            continue
        run_id = str(summary.get("run_id") or summary_path.parent.name)
        for case in summary.get("cases") or []:
            if not isinstance(case, dict):
                continue
            usage = case.get("asset_usage") or {}
            outcome = _status(case.get("verdict"))
            failure_class = str(case.get("failure_class") or "")
            cleanup_failed = case.get("cleanup_ok") is False
            for asset_type, asset_id in _asset_refs(usage):
                key = (asset_type, asset_id)
                stats = assets.setdefault(key, _new_stats(asset_type, asset_id))
                stats["runs"] += 1
                stats["run_ids"].append(run_id)
                stats["cases"].append(str(case.get("case_id") or ""))
                if outcome == "pass":
                    stats["passes"] += 1
                    stats["consecutive_failures"] = 0
                elif outcome == "inconclusive":
                    stats["inconclusive"] += 1
                    stats["consecutive_failures"] += 1
                elif outcome == "blocked":
                    stats["blocked"] += 1
                    stats["consecutive_failures"] += 1
                else:
                    stats["failures"] += 1
                    stats["consecutive_failures"] += 1
                stats["max_consecutive_failures"] = max(stats["max_consecutive_failures"], stats["consecutive_failures"])
                if cleanup_failed:
                    stats["cleanup_failures"] += 1
                if failure_class:
                    counts = Counter(stats["failure_classes"])
                    counts[failure_class] += 1
                    stats["failure_classes"] = dict(counts)
    for stats in assets.values():
        stats["success_rate"] = round(stats["passes"] / stats["runs"], 4) if stats["runs"] else 0.0
        stats["failure_rate"] = round((stats["failures"] + stats["blocked"] + stats["inconclusive"]) /
                                       stats["runs"], 4) if stats["runs"] else 0.0
        stats["health"] = _health(stats, degrade_after=degrade_after, unhealthy_after=unhealthy_after)
    rows = sorted(assets.values(), key=lambda item: (item["health"] != "unhealthy", item["health"], item["asset_id"]))
    return {"schema_version": 1, "runs_root": str(root), "run_count": len(summaries),
            "asset_count": len(rows), "assets": rows}


def _asset_path(suite_dir: Path, asset_type: str, asset_id: str) -> Path:
    folder = "fixtures" if asset_type == "fixture" else "oracles"
    safe = "".join(char if char.isalnum() or char in "._-" else "_" for char in asset_id)
    return suite_dir / "approved_assets" / folder / f"{safe}.yaml"


def update_approved_asset_health(suite_dir: str | Path, report: dict[str, Any]) -> list[str]:
    """Persist health only; approval/status and content hash remain unchanged."""
    updated: list[str] = []
    root = Path(suite_dir)
    for row in report.get("assets") or []:
        path = _asset_path(root, str(row["asset_type"]), str(row["asset_id"]))
        if not path.is_file():
            continue
        try:
            asset = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        if asset.get("status") != "approved" or not asset.get("approved_by"):
            continue
        asset["health"] = {
            "status": row["health"], "runs": row["runs"], "success_rate": row["success_rate"],
            "failure_rate": row["failure_rate"], "consecutive_failures": row["consecutive_failures"],
            "max_consecutive_failures": row["max_consecutive_failures"],
            "failure_classes": row["failure_classes"],
        }
        temporary = path.with_suffix(".tmp")
        temporary.write_text(yaml.safe_dump(asset, allow_unicode=True, sort_keys=False), encoding="utf-8")
        temporary.replace(path)
        updated.append(str(path))
    return updated


def write_asset_health(report: dict[str, Any], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
