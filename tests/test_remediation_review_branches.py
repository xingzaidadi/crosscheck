"""remediation_review 分支覆盖(离线、零业务):草稿复核→安全晋级为 approved 资产。

run_tests.py 把 test_*.py 当脚本跑(returncode==0 即过),纯 pytest 风格不贡献覆盖。
本文件 main()+assert 真实执行,补 load_plan 模式门禁、_find_draft 查找、validate_draft 的
fixture(strategy/steps/cleanup)与 oracle(assertions/id 去重/proof 白名单/expected)各分支、
review_draft 的 reviewer/decision 门禁 + approve 落盘 + reject 不落盘 + 审计/任务联动。
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

from core.remediation_review import (  # noqa: E402
    load_plan, validate_draft, review_draft, _find_draft, _hash,
)


def _good_fixture():
    return {"fixture_id": "fixture:seed", "strategy": "api-seed",
            "steps": [{"action": "POST /api/seed"}],
            "cleanup_contract": {"required": True, "declared": True}}


def _good_oracle():
    return {"oracle_id": "oracle:status",
            "assertions": [{"id": "a1", "proof": "api_response", "expected": 200}]}


def _plan(**extra):
    p = {"mode": "review_only", "fixture_drafts": [], "oracle_drafts": [], "tasks": []}
    p.update(extra)
    return p


def test_load_plan_mode_gate():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "plan.json"
        # 非 review_only → 拒
        p.write_text(json.dumps({"mode": "auto"}), encoding="utf-8")
        try:
            load_plan(p)
        except ValueError as e:
            assert "review_only" in str(e)
        else:
            raise AssertionError("非 review_only 计划必须拒")
        # 合法 review_only → 读
        p.write_text(json.dumps(_plan()), encoding="utf-8")
        assert load_plan(p)["mode"] == "review_only"
        # 非 dict(数组)→ 拒
        p.write_text(json.dumps([1, 2]), encoding="utf-8")
        try:
            load_plan(p)
        except ValueError:
            pass
        else:
            raise AssertionError("非 dict 计划必须拒")
    print("  ✓ load_plan:仅 mode==review_only 的 dict 放行,其余拒")


def test_find_draft_fixture_oracle_and_missing():
    plan = _plan(fixture_drafts=[_good_fixture()], oracle_drafts=[_good_oracle()])
    assert _find_draft(plan, "fixture:seed")[0] == "fixture"
    assert _find_draft(plan, "oracle:status")[0] == "oracle"
    try:
        _find_draft(plan, "nope")
    except ValueError as e:
        assert "not found" in str(e)
    else:
        raise AssertionError("未知 asset_id 必须抛")
    print("  ✓ _find_draft:fixture/oracle 命中,未知 id 抛")


def test_validate_fixture_branches():
    # strategy 未选
    d = _good_fixture(); d["strategy"] = "needs_review"
    assert any("strategy" in e for e in validate_draft("fixture", d))
    # steps 空
    d = _good_fixture(); d["steps"] = []
    assert any("steps" in e for e in validate_draft("fixture", d))
    # cleanup 未声明
    d = _good_fixture(); d["cleanup_contract"] = {"required": True, "declared": False}
    assert any("cleanup_contract" in e for e in validate_draft("fixture", d))
    # 合法 → 无错
    assert validate_draft("fixture", _good_fixture()) == []
    print("  ✓ validate_draft(fixture):strategy/steps/cleanup 三闸,合法放行")


def test_validate_oracle_branches():
    # assertions 空
    assert any("assertions" in e for e in validate_draft("oracle", {"assertions": []}))
    # 条目非对象
    assert any("must be an object" in e for e in
               validate_draft("oracle", {"assertions": ["x"]}))
    # 缺 id + proof 不在白名单 + 缺 expected
    errs = validate_draft("oracle", {"assertions": [{"proof": "telepathy"}]})
    assert any("id is required" in e for e in errs)
    assert any("proof is unsupported" in e for e in errs)
    assert any("expected is required" in e for e in errs)
    # id 重复
    errs = validate_draft("oracle", {"assertions": [
        {"id": "a", "proof": "ui", "expected": 1},
        {"id": "a", "proof": "ui", "expected": 2}]})
    assert any("duplicated" in e for e in errs)
    # 合法(proof 认别名 ui/api/db)→ 无错
    assert validate_draft("oracle", _good_oracle()) == []
    assert validate_draft("oracle", {"assertions": [
        {"id": "a", "kind": "db", "expected": 0}]}) == []   # proof 可走 kind
    print("  ✓ validate_draft(oracle):空/非对象/缺id/proof白名单/缺expected/id重复,别名放行")


def test_validate_unsupported_type():
    assert any("unsupported asset type" in e for e in validate_draft("wat", {}))
    print("  ✓ validate_draft:未知资产类型报错")


def _seed_plan(tmp, **drafts):
    p = Path(tmp) / "plan.json"
    plan = _plan(**drafts)
    plan["tasks"] = [{"draft_asset_id": next(iter(
        [d.get("fixture_id") or d.get("oracle_id")
         for lst in drafts.values() for d in lst])), "status": "pending"}]
    p.write_text(json.dumps(plan), encoding="utf-8")
    return p


def test_review_reject_does_not_write_asset():
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _seed_plan(tmp, fixture_drafts=[_good_fixture()])
        suite = Path(tmp) / "suite"
        res = review_draft(plan_path, suite, "fixture:seed",
                           reviewer="qa", decision="reject")
        assert res["decision"] == "reject" and res["approved_asset"] is None
        # 落盘计划里 draft 与 task 都标 rejected,approved_by 清空
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        draft = plan["fixture_drafts"][0]
        assert draft["status"] == "rejected" and draft["approved_by"] == ""
        assert plan["tasks"][0]["status"] == "rejected"
        assert plan["review_audit"][0]["decision"] == "reject"
        # 不生成 approved_assets 资产文件
        assert not (suite / "approved_assets").exists()
    print("  ✓ review_draft(reject):标 rejected、不落盘资产、审计留痕")


def test_review_approve_writes_asset_and_hash_stable():
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _seed_plan(tmp, oracle_drafts=[_good_oracle()])
        suite = Path(tmp) / "suite"
        res = review_draft(plan_path, suite, "oracle:status",
                           reviewer="qa", decision="approve",
                           evidence=["run/123/summary.json"])
        assert res["decision"] == "approve"
        asset_path = Path(res["approved_asset"])
        assert asset_path.is_file() and asset_path.parent.name == "oracles"
        asset = yaml.safe_load(asset_path.read_text(encoding="utf-8"))
        assert asset["status"] == "approved" and asset["approved_by"] == "qa"
        assert asset["review_evidence"] == ["run/123/summary.json"]
        # content_hash 排除易变字段,可独立复算一致
        recomputed = _hash({k: v for k, v in asset.items()
                            if k not in {"content_hash", "reviewed_at", "review_evidence"}})
        assert asset["content_hash"] == recomputed == res["content_hash"]
        # task 联动 approved
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        assert plan["tasks"][0]["status"] == "approved"
    print("  ✓ review_draft(approve):落盘 approved 资产、task 联动、content_hash 可复算")


def test_review_approve_blocks_invalid_draft():
    with tempfile.TemporaryDirectory() as tmp:
        bad = _good_fixture(); bad["steps"] = []       # 不可晋级
        plan_path = _seed_plan(tmp, fixture_drafts=[bad])
        try:
            review_draft(plan_path, Path(tmp) / "suite", "fixture:seed",
                         reviewer="qa", decision="approve")
        except ValueError as e:
            assert "not approvable" in str(e)
        else:
            raise AssertionError("不合格草稿不得晋级")
    print("  ✓ review_draft(approve):校验不过的草稿拒绝晋级(门禁)")


def test_review_guards_reviewer_and_decision():
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _seed_plan(tmp, fixture_drafts=[_good_fixture()])
        suite = Path(tmp) / "suite"
        for kwargs, needle in (
            ({"reviewer": "  ", "decision": "approve"}, "reviewer is required"),
            ({"reviewer": "qa", "decision": "maybe"}, "approve or reject")):
            try:
                review_draft(plan_path, suite, "fixture:seed", **kwargs)
            except ValueError as e:
                assert needle in str(e), str(e)
            else:
                raise AssertionError(f"应拒:{kwargs}")
    print("  ✓ review_draft:空 reviewer、非法 decision 一律拒")


def test_review_updates_applied_before_validation():
    with tempfile.TemporaryDirectory() as tmp:
        # 起始草稿缺 strategy,通过 updates 现场补齐后可晋级
        draft = _good_fixture(); draft["strategy"] = "needs_review"
        plan_path = _seed_plan(tmp, fixture_drafts=[draft])
        res = review_draft(plan_path, Path(tmp) / "suite", "fixture:seed",
                           reviewer="qa", decision="approve",
                           updates={"strategy": "api-seed"})
        assert res["decision"] == "approve"
        asset = yaml.safe_load(Path(res["approved_asset"]).read_text(encoding="utf-8"))
        assert asset["strategy"] == "api-seed" and asset["verified"] is True
    print("  ✓ review_draft:updates 先合入再校验(人审补齐后放行,fixture 置 verified)")


def main():
    test_load_plan_mode_gate()
    test_find_draft_fixture_oracle_and_missing()
    test_validate_fixture_branches()
    test_validate_oracle_branches()
    test_validate_unsupported_type()
    test_review_reject_does_not_write_asset()
    test_review_approve_writes_asset_and_hash_stable()
    test_review_approve_blocks_invalid_draft()
    test_review_guards_reviewer_and_decision()
    test_review_updates_applied_before_validation()
    print("\n全部通过 ✅  —— remediation_review 分支覆盖(计划门禁/查找/校验/复核落盘)")


if __name__ == "__main__":
    main()
