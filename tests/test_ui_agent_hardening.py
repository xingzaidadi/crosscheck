from core.asset_pipeline import auto_promote_read_only, create_candidate, record_replay
from core.ui_agent.hardening import find_reusable_asset, harden_run


def test_stable_read_only_asset_becomes_provisional(tmp_path):
    result = harden_run(
        workspace=tmp_path,
        plan={"plan_id": "NL-1", "url": "https://example.test", "actions": [], "oracles": [],
              "write_risk": False, "source_instruction": "检查首页"},
        result={"status": "PASSED", "evidence": ["before.png", "after.png"]},
    )
    assert result["state"] == "provisional"


def test_stable_asset_is_reusable_by_same_url_and_instruction(tmp_path):
    plan = {"plan_id": "NL-1", "url": "https://example.test", "actions": [], "oracles": [],
            "write_risk": False, "source_instruction": "检查首页"}
    harden_run(workspace=tmp_path, plan=plan,
               result={"status": "PASSED", "evidence": ["before.png", "after.png"]})
    asset = find_reusable_asset(tmp_path, plan)
    assert asset is not None
    assert asset["state"] == "provisional"


def test_write_asset_cannot_auto_promote():
    asset = create_candidate({"write_risk": True})
    asset = record_replay(asset, passed=True, original_result={}, replay_result={}, evidence=["x"])
    asset = record_replay(asset, passed=True, original_result={}, replay_result={}, evidence=["x"])
    try:
        auto_promote_read_only(asset, evidence=["x"])
    except ValueError as exc:
        assert "write-risk" in str(exc)
    else:
        raise AssertionError("write asset should require review")
