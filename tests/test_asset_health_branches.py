"""asset_health 分支覆盖(离线、零业务):资产健康聚合的全档位与写回门禁。

仓库 run_tests.py 把每个 test_*.py 当脚本跑(returncode==0 即过),纯 pytest 风格
(只有 def test_(tmp_path) 无 main)在它下面是空过、不贡献覆盖。本文件用 main()+assert
风格真实执行,打满 aggregate 的 pass/inconclusive/blocked/fail 四分支、_health 三档、
update 的审批门禁与跳过路径、write 落盘——补平 asset_health 的真实覆盖。
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import yaml  # noqa: E402

from core.asset_health import (  # noqa: E402
    aggregate_asset_health, update_approved_asset_health, write_asset_health,
    _status, _health, _asset_refs, _new_stats,
)


def _mk_summary(runs: Path, run_id: str, verdict: str, *, failure_class="",
                cleanup_ok=True, asset_id="fixture:one", kind="fixture"):
    d = runs / run_id
    d.mkdir(parents=True)
    (d / "summary.json").write_text(json.dumps({
        "run_id": run_id,
        "cases": [{
            "case_id": "suite/TC1", "verdict": verdict, "failure_class": failure_class,
            "cleanup_ok": cleanup_ok,
            "asset_usage": {kind: {"asset_id": asset_id}},
        }],
    }), encoding="utf-8")


def test_status_maps_all_verdicts():
    assert _status("pass") == "pass"
    assert _status("passed") == "pass"
    assert _status("partial") == "inconclusive"
    assert _status("unknown") == "inconclusive"
    assert _status("inconclusive") == "inconclusive"
    assert _status("skip") == "blocked"
    assert _status("blocked") == "blocked"
    assert _status("invalid_spec") == "blocked"
    assert _status("env_error") == "blocked"
    assert _status("fail") == "fail"
    assert _status("") == "fail"            # 空/未知一律保守判 fail
    assert _status(None) == "fail"
    print("  ✓ _status 覆盖 pass/inconclusive/blocked/fail 全映射(未知保守判 fail)")


def test_health_tiers():
    # insufficient_data:零运行
    base = _new_stats("fixture", "x"); base["runs"] = 0; base["success_rate"] = 0.0
    assert _health(base, degrade_after=2, unhealthy_after=3) == "insufficient_data"
    # healthy:全通过
    ok = _new_stats("fixture", "x"); ok.update(runs=10, consecutive_failures=0, success_rate=1.0)
    assert _health(ok, degrade_after=2, unhealthy_after=3) == "healthy"
    # degraded:成功率 < 0.95(连败未到门槛)
    deg = _new_stats("fixture", "x"); deg.update(runs=10, consecutive_failures=1, success_rate=0.9)
    assert _health(deg, degrade_after=2, unhealthy_after=3) == "degraded"
    # degraded:连败达降级门槛但未到不健康
    deg2 = _new_stats("fixture", "x"); deg2.update(runs=10, consecutive_failures=2, success_rate=0.99)
    assert _health(deg2, degrade_after=2, unhealthy_after=3) == "degraded"
    # unhealthy:连败达不健康门槛
    bad = _new_stats("fixture", "x"); bad.update(runs=10, consecutive_failures=3, success_rate=0.5)
    assert _health(bad, degrade_after=2, unhealthy_after=3) == "unhealthy"
    print("  ✓ _health 覆盖 insufficient_data/healthy/degraded/unhealthy 四档")


def test_asset_refs_picks_fixture_and_oracle():
    refs = _asset_refs({"fixture": {"asset_id": "f1"}, "oracle": {"asset_id": "o1"},
                        "other": {"asset_id": "ignored"}})
    assert ("fixture", "f1") in refs and ("oracle", "o1") in refs
    assert all(k in ("fixture", "oracle") for k, _ in refs)   # 只认 fixture/oracle
    assert _asset_refs({"fixture": {}}) == []                 # 无 asset_id 不计
    assert _asset_refs({}) == []
    print("  ✓ _asset_refs 只提取 fixture/oracle 且必须有 asset_id")


def test_aggregate_consecutive_reset_on_pass_and_health_healthy():
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        # fail, fail, pass → 连败归零;再全 pass → healthy
        _mk_summary(runs, "r1", "fail", failure_class="TARGET_FAIL")
        _mk_summary(runs, "r2", "fail", failure_class="TARGET_FAIL")
        _mk_summary(runs, "r3", "pass")
        for i in range(4, 42):
            _mk_summary(runs, f"r{i}", "pass")
        rep = aggregate_asset_health(runs)
        fx = next(a for a in rep["assets"] if a["asset_type"] == "fixture")
        assert fx["consecutive_failures"] == 0, fx["consecutive_failures"]   # pass 清零
        assert fx["max_consecutive_failures"] == 2                           # 峰值留痕
        assert fx["passes"] == 39 and fx["failures"] == 2                    # 39/41≈0.951≥0.95
        assert fx["health"] == "healthy", (fx["success_rate"], fx["health"])
    print("  ✓ aggregate:pass 清零连败、留峰值,高成功率判 healthy")


def test_aggregate_inconclusive_and_blocked_and_cleanup():
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        _mk_summary(runs, "r1", "partial")                       # inconclusive
        _mk_summary(runs, "r2", "blocked", cleanup_ok=False)     # blocked + 清理失败
        rep = aggregate_asset_health(runs)
        fx = next(a for a in rep["assets"] if a["asset_type"] == "fixture")
        assert fx["inconclusive"] == 1 and fx["blocked"] == 1
        assert fx["cleanup_failures"] == 1
        assert fx["consecutive_failures"] == 2                   # 两者都累计连败
        # 两次非 pass → 失败率 1.0、成功率 0
        assert fx["success_rate"] == 0.0 and fx["failure_rate"] == 1.0
    print("  ✓ aggregate:inconclusive/blocked 都累计连败,cleanup_ok=False 计清理失败")


def test_aggregate_sorts_unhealthy_first_and_skips_bad_summary():
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        # fixture 全败 → unhealthy;oracle 全过 → healthy。排序后 unhealthy 在前。
        for i in range(3):
            _mk_summary(runs, f"f{i}", "fail", asset_id="fixture:bad", kind="fixture")
        for i in range(3):
            _mk_summary(runs, f"o{i}", "pass", asset_id="oracle:good", kind="oracle")
        # 损坏 summary.json 必须被跳过、不崩
        bad = runs / "broken"; bad.mkdir()
        (bad / "summary.json").write_text("{not json", encoding="utf-8")
        rep = aggregate_asset_health(runs)
        assert rep["asset_count"] == 2
        assert rep["assets"][0]["health"] == "unhealthy", [a["health"] for a in rep["assets"]]
        assert rep["run_count"] == 7                             # glob 到 7 个文件;损坏那条仅不参与聚合
        # 聚合只纳入有效 summary:两资产各 3 次 run,损坏文件未污染统计
        assert all(a["runs"] == 3 for a in rep["assets"])
    print("  ✓ aggregate:unhealthy 排最前、损坏 summary 跳过不污染聚合")


def test_update_gated_by_approval():
    with tempfile.TemporaryDirectory() as tmp:
        suite = Path(tmp) / "suite"
        fx_dir = suite / "approved_assets" / "fixtures"
        fx_dir.mkdir(parents=True)
        # 已审批 → 写回 health
        (fx_dir / "fixture_ok.yaml").write_text(yaml.safe_dump({
            "fixture_id": "fixture:ok", "status": "approved", "approved_by": "qa",
            "content_hash": "h"}), encoding="utf-8")
        # 草稿(非 approved)→ 不碰
        (fx_dir / "fixture_draft.yaml").write_text(yaml.safe_dump({
            "fixture_id": "fixture:draft", "status": "draft"}), encoding="utf-8")
        # approved 但缺 approved_by → 不碰(门禁双条件)
        (fx_dir / "fixture_noby.yaml").write_text(yaml.safe_dump({
            "fixture_id": "fixture:noby", "status": "approved"}), encoding="utf-8")

        def _row(aid):
            return {"asset_type": "fixture", "asset_id": aid, "health": "degraded",
                    "runs": 2, "success_rate": 0.5, "failure_rate": 0.5,
                    "consecutive_failures": 1, "max_consecutive_failures": 1,
                    "failure_classes": {}}
        report = {"assets": [_row("fixture:ok"), _row("fixture:draft"),
                             _row("fixture:noby"), _row("fixture:missing")]}
        updated = update_approved_asset_health(suite, report)
        # 只有 fixture:ok 被更新;draft/noby/missing 一律跳过
        assert len(updated) == 1 and "fixture_ok.yaml" in updated[0], updated
        ok = yaml.safe_load((fx_dir / "fixture_ok.yaml").read_text(encoding="utf-8"))
        assert ok["health"]["status"] == "degraded" and ok["content_hash"] == "h"
        draft = yaml.safe_load((fx_dir / "fixture_draft.yaml").read_text(encoding="utf-8"))
        assert "health" not in draft, "非 approved 资产不得被写回 health"
    print("  ✓ update:仅 status=approved 且有 approved_by 才写回,草稿/缺审批人/缺文件跳过")


def test_write_asset_health_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "nested" / "asset-health.json"
        rep = {"schema_version": 1, "asset_count": 0, "assets": []}
        p = write_asset_health(rep, out)
        assert p.is_file() and json.loads(p.read_text(encoding="utf-8"))["schema_version"] == 1
    print("  ✓ write_asset_health 落盘(自建父目录,可回读)")


def main():
    test_status_maps_all_verdicts()
    test_health_tiers()
    test_asset_refs_picks_fixture_and_oracle()
    test_aggregate_consecutive_reset_on_pass_and_health_healthy()
    test_aggregate_inconclusive_and_blocked_and_cleanup()
    test_aggregate_sorts_unhealthy_first_and_skips_bad_summary()
    test_update_gated_by_approval()
    test_write_asset_health_roundtrip()
    print("\n全部通过 ✅  —— asset_health 分支覆盖(聚合四档位/健康三档/写回门禁)")


if __name__ == "__main__":
    main()
