"""Unified CI quality gate for business-suite readiness and asset health."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .asset_health import aggregate_asset_health
from .soak_report import aggregate_soak, build_soak_summary
from .domain_capability_readiness import assess_domain_capabilities
from .product_readiness import assess_product_readiness
from .suite_dsl import load_suite


MATURITY_ORDER = ("M0", "M1", "M2", "M3", "M4")


def _at_least(actual: str, required: str) -> bool:
    try:
        return MATURITY_ORDER.index(actual) >= MATURITY_ORDER.index(required)
    except ValueError:
        return False


def _load_json(path: str | Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return value if isinstance(value, dict) else None


def evaluate_quality_gate(
    product_report: dict[str, Any],
    asset_report: dict[str, Any],
    *,
    domain_report: dict[str, Any] | None = None,
    min_capability_coverage: float = 1.0,
    require_capability_pack: bool = True,
    min_score: float = 75.0,
    min_maturity: str = "M3",
    min_preparation: float = 1.0,
    min_oracle: float = 1.0,
    max_inconclusive: float = 0.10,
    max_degraded_assets: int = 0,
    max_unhealthy_assets: int = 0,
    require_run_evidence: bool = True,
    mode: str = "enforce",
    verified_via: list[str] | None = None,
    reviewed_by: str = "",
) -> dict[str, Any]:
    """Evaluate a strict, explainable gate without changing any assets."""
    if mode not in ("off", "observe", "enforce"):
        raise ValueError("mode must be off, observe or enforce")
    maturity = product_report.get("maturity") or {}
    dimensions = maturity.get("dimensions") or {}
    blockers: list[dict[str, Any]] = []
    score = float(maturity.get("score") or 0)
    maturity_level = str(maturity.get("level") or "M0")
    if mode == "off":
        # Skip judgment entirely; nothing is computed or blocked.
        return _finalize_gate(
            maturity_level, score, dimensions, {}, {}, blockers, mode,
            skipped=True, verified_via=verified_via, reviewed_by=reviewed_by,
            policy=_policy_dict(min_score, min_maturity, min_preparation, min_oracle,
                                max_inconclusive, max_degraded_assets, max_unhealthy_assets,
                                require_run_evidence, min_capability_coverage, require_capability_pack),
        )
    if score < min_score:
        blockers.append({"type": "maturity_score", "actual": score, "required": min_score,
                         "action": "提升 READY、审批、绑定、前置状态、Oracle 和稳定性覆盖"})
    if not _at_least(maturity_level, min_maturity):
        blockers.append({"type": "maturity_level", "actual": maturity_level, "required": min_maturity,
                         "action": "完成从受控执行到流水线无人值守的生产化验收"})
    preparation = float(dimensions.get("preparation") or 0)
    if preparation < min_preparation:
        blockers.append({"type": "preparation_coverage", "actual": preparation, "required": min_preparation,
                         "action": "补充并批准 Fixture、State Recipe 或 Capability Pack"})
    oracle = float(dimensions.get("oracle") or 0)
    if oracle < min_oracle:
        blockers.append({"type": "oracle_coverage", "actual": oracle, "required": min_oracle,
                         "action": "补充结构化业务 Oracle 和可复核证明来源"})
    inconclusive = float(dimensions.get("inconclusive_rate") or 0)
    if inconclusive > max_inconclusive:
        blockers.append({"type": "inconclusive_rate", "actual": inconclusive, "required": max_inconclusive,
                         "action": "补齐跨层、异步或日志证据，减少无法判定结果"})
    if require_run_evidence and not dimensions.get("has_run_evidence"):
        blockers.append({"type": "run_evidence_missing", "actual": False, "required": True,
                         "action": "执行 pilot/soak 并生成带资产来源的 summary.json"})

    health_counts = {
        status: sum(item.get("health") == status for item in asset_report.get("assets") or [])
        for status in ("healthy", "degraded", "unhealthy", "insufficient_data")
    }
    if health_counts["degraded"] > max_degraded_assets:
        blockers.append({"type": "degraded_assets", "actual": health_counts["degraded"],
                         "required": max_degraded_assets, "action": "修复并重新认证 degraded 资产"})
    if health_counts["unhealthy"] > max_unhealthy_assets:
        blockers.append({"type": "unhealthy_assets", "actual": health_counts["unhealthy"],
                         "required": max_unhealthy_assets, "action": "隔离 unhealthy 资产并完成重新认证"})

    domain = domain_report or {}
    capability_coverage = float(domain.get("coverage") or 0.0) if domain else 0.0
    capability_valid = bool(domain.get("capability_pack_valid")) if domain else False
    if domain:
        if require_capability_pack and not capability_valid:
            blockers.append({"type": "capability_pack_invalid", "actual": capability_valid, "required": True,
                             "action": "为业务域提供校验通过的 capability pack"})
        if capability_coverage < min_capability_coverage:
            blockers.append({"type": "capability_coverage", "actual": capability_coverage,
                             "required": min_capability_coverage,
                             "action": "补齐前置动作对应的创建/状态推进/查询/清理能力"})

    return _finalize_gate(
        maturity_level, score,
        {"preparation": preparation, "oracle": oracle, "inconclusive_rate": inconclusive,
         "has_run_evidence": bool(dimensions.get("has_run_evidence"))},
        {"counts": health_counts, "total": int(asset_report.get("asset_count") or 0)},
        {"coverage": capability_coverage, "valid": capability_valid,
         "missing_action_kinds": list(domain.get("missing_action_kinds") or []) if domain else []},
        blockers, mode, skipped=False, verified_via=verified_via, reviewed_by=reviewed_by,
        policy=_policy_dict(min_score, min_maturity, min_preparation, min_oracle,
                            max_inconclusive, max_degraded_assets, max_unhealthy_assets,
                            require_run_evidence, min_capability_coverage, require_capability_pack),
    )


def _policy_dict(min_score, min_maturity, min_preparation, min_oracle, max_inconclusive,
                 max_degraded_assets, max_unhealthy_assets, require_run_evidence,
                 min_capability_coverage, require_capability_pack) -> dict[str, Any]:
    return {
        "min_score": min_score, "min_maturity": min_maturity,
        "min_preparation": min_preparation, "min_oracle": min_oracle,
        "max_inconclusive": max_inconclusive, "max_degraded_assets": max_degraded_assets,
        "max_unhealthy_assets": max_unhealthy_assets, "require_run_evidence": require_run_evidence,
        "min_capability_coverage": min_capability_coverage, "require_capability_pack": require_capability_pack,
    }


def _verification_stamp(mode: str, verified_via: list[str] | None, reviewed_by: str,
                        passed: bool) -> dict[str, Any]:
    via = list(verified_via) if verified_via else ["none"]
    stamp = {
        "reviewed_by": reviewed_by,
        "verified_via": via,
        "mode": mode,
        "passed": passed,
        "at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    hashable = {k: v for k, v in stamp.items() if k != "at"}
    digest = hashlib.sha256(
        json.dumps(hashable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    stamp["content_hash"] = f"sha256:{digest}"
    return stamp


def _finalize_gate(maturity_level, score, dimensions, asset_health, capability,
                   blockers, mode, *, skipped, verified_via, reviewed_by, policy) -> dict[str, Any]:
    # enforce: blockers really fail the gate. observe: compute but never block.
    enforced_block = bool(blockers) and mode == "enforce"
    would_block = list(blockers) if mode == "observe" else []
    passed = not enforced_block
    return {
        "schema_version": 1,
        "mode": mode,
        "skipped": skipped,
        "passed": passed,
        "production_ready": passed and not blockers,
        "enforced_block": enforced_block,
        "would_block": would_block,
        "maturity": {"level": maturity_level, "score": score},
        "dimensions": dimensions,
        "asset_health": asset_health,
        "capability": capability,
        "policy": policy,
        "blockers": blockers,
        "next_actions": [item["action"] for item in blockers],
        "verification_stamp": _verification_stamp(mode, verified_via, reviewed_by, passed),
    }


def build_quality_gate(
    suite_dir: str | Path,
    workspace: str | Path,
    *,
    run_report: str | Path | None = None,
    asset_report: str | Path | None = None,
    **policy: Any,
) -> dict[str, Any]:
    suite_path = Path(suite_dir)
    suite, cases = load_suite(suite_path)
    run_data = _load_json(run_report)
    soak = aggregate_soak(suite_path / "reports" / "runs")
    if run_data is None and soak["soak_runs"]:
        run_data = build_soak_summary(soak)
    product = assess_product_readiness(suite, cases, run_report=run_data,
                                       suite_dir=suite_path, workspace=workspace)
    assets = _load_json(asset_report) if asset_report else None
    if assets is None:
        assets = aggregate_asset_health(suite_path / "reports" / "runs")
    registry = Path(workspace) / "config" / "capabilities.yaml"
    domain = assess_domain_capabilities(cases, registry_path=registry,
                                        environment=str(suite.get("environment") or "test"))
    gate = evaluate_quality_gate(product, assets, domain_report=domain, **policy)
    gate["suite_id"] = suite.get("suite_id", "")
    gate["product_readiness"] = product
    gate["asset_health_report"] = assets
    gate["domain_capability_report"] = domain
    gate["soak"] = {"soak_runs": soak["soak_runs"], "stability": soak["stability"],
                    "meets_min_runs": soak["meets_min_runs"], "all_runs_passed": soak["all_runs_passed"]}
    return gate


def write_quality_gate(report: dict[str, Any], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
