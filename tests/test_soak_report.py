import json

from core.soak_report import aggregate_soak, build_soak_summary


def _write_run(root, run_id, cases):
    path = root / run_id
    path.mkdir(parents=True)
    (path / "summary.json").write_text(json.dumps({"run_id": run_id, "cases": cases}), encoding="utf-8")


def _case(case_id, verdict, asset_id="fixture:one"):
    return {"case_id": case_id, "verdict": verdict,
            "asset_usage": {"fixture": {"asset_id": asset_id}}}


def test_soak_aggregates_stability_and_per_case_pass_rate(tmp_path):
    runs = tmp_path / "runs"
    _write_run(runs, "r1", [_case("s/TC1", "PASS"), _case("s/TC2", "PASS")])
    _write_run(runs, "r2", [_case("s/TC1", "PASS"), _case("s/TC2", "FAIL")])
    report = aggregate_soak(runs, min_runs=2)
    assert report["soak_runs"] == 2
    assert report["passed_runs"] == 1
    assert report["stability"] == 0.5
    assert report["meets_min_runs"] is True
    assert report["all_runs_passed"] is False
    tc2 = next(item for item in report["per_case"] if item["case_id"] == "s/TC2")
    assert tc2["pass_rate"] == 0.5


def test_soak_summary_is_quality_gate_consumable(tmp_path):
    runs = tmp_path / "runs"
    for run_id in ("r1", "r2", "r3", "r4", "r5"):
        _write_run(runs, run_id, [_case("s/TC1", "PASS")])
    report = aggregate_soak(runs, min_runs=5)
    summary = build_soak_summary(report)
    assert summary["soak_runs"] == 5
    assert summary["total"] == 5
    assert summary["pass"] == 5
    assert summary["inconclusive"] == 0
    assert all(case["verdict"] == "PASS" for case in summary["cases"])
    assert report["all_runs_passed"] is True


def test_soak_counts_only_real_summaries(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "empty").mkdir()
    report = aggregate_soak(runs, min_runs=5)
    assert report["soak_runs"] == 0
    assert report["meets_min_runs"] is False
