import pytest

from core.asset_pipeline import create_candidate, record_replay
from core.asset_review import accept_replay_verified, activate_reviewed, review_queue
from core.asset_store import AssetStore


def test_replay_assets_enter_explicit_human_review_queue(tmp_path):
    store = AssetStore(tmp_path / "assets")
    asset = create_candidate({"case_id": "TC1", "required_review": ["selector"]})
    store.save(asset)
    with pytest.raises(ValueError):
        accept_replay_verified(store, asset["asset_id"], reviewer="qa")
    replayed = record_replay(asset, passed=True, original_result={}, replay_result={"ok": True},
                             evidence=["shot.png"])
    store.save(replayed)
    assert review_queue(store)[0]["state"] == "replay_verified"
    accepted = accept_replay_verified(store, asset["asset_id"], reviewer="qa")
    assert accepted["state"] == "human_verified"
    active = activate_reviewed(store, asset["asset_id"], reviewer="qa-lead")
    assert active["state"] == "active"
    assert store.executable(asset["asset_id"]) is True
