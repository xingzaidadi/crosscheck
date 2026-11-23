import json

import yaml

from core.asset_health import aggregate_asset_health, update_approved_asset_health
from core.approved_assets import load_approved_assets


def _summary(root, run_id, verdict, failure_class=""):
    path = root / run_id
    path.mkdir(parents=True)
    (path / "summary.json").write_text(json.dumps({
        "run_id": run_id,
        "cases": [{
            "case_id": "suite/TC1", "verdict": verdict, "failure_class": failure_class,
            "cleanup_ok": True,
            "asset_usage": {"fixture": {"asset_id": "fixture:one"},
                             "oracle": {"asset_id": "oracle:one"}},
        }],
    }), encoding="utf-8")


def test_asset_health_aggregates_failures_and_consecutive_failures(tmp_path):
    runs = tmp_path / "runs"
    _summary(runs, "r1", "pass")
    _summary(runs, "r2", "fail", "TARGET_FAIL")
    _summary(runs, "r3", "env_error", "ENV_ERROR")
    report = aggregate_asset_health(runs)
    fixture = next(item for item in report["assets"] if item["asset_type"] == "fixture")
    assert fixture["runs"] == 3
    assert fixture["success_rate"] == round(1 / 3, 4)
    assert fixture["consecutive_failures"] == 2
    assert fixture["health"] == "degraded"
    assert fixture["failure_classes"] == {"TARGET_FAIL": 1, "ENV_ERROR": 1}


def test_update_health_preserves_approval_and_content_hash(tmp_path):
    suite = tmp_path / "suite"
    path = suite / "approved_assets" / "fixtures" / "fixture_one.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump({"fixture_id": "fixture:one", "status": "approved",
                                    "approved_by": "qa", "content_hash": "original"}), encoding="utf-8")
    report = {"assets": [{"asset_type": "fixture", "asset_id": "fixture:one", "health": "degraded",
                           "runs": 2, "success_rate": 0.5, "failure_rate": 0.5,
                           "consecutive_failures": 2, "max_consecutive_failures": 2,
                           "failure_classes": {"TARGET_FAIL": 1}}]}
    updated = update_approved_asset_health(suite, report)
    asset = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert updated and asset["status"] == "approved"
    assert asset["content_hash"] == "original"
    assert asset["health"]["status"] == "degraded"


def test_unhealthy_approved_asset_is_not_loaded_for_execution(tmp_path):
    root = tmp_path / "suite" / "approved_assets" / "oracles"
    root.mkdir(parents=True)
    (root / "oracle.yaml").write_text(yaml.safe_dump({
        "oracle_id": "oracle:bad", "case_id": "suite/TC1", "status": "approved",
        "approved_by": "qa", "health": {"status": "unhealthy"},
    }), encoding="utf-8")
    assert load_approved_assets(tmp_path / "suite", "oracles") == []
