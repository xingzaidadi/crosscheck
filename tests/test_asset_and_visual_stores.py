from pathlib import Path

from PIL import Image

from core.asset_pipeline import create_candidate, record_replay
from core.asset_store import AssetStore
from core.visual_store import VisualBaselineStore


def test_asset_store_persists_review_transitions(tmp_path: Path):
    store = AssetStore(tmp_path / "assets")
    asset = create_candidate({"action": "click"})
    store.save(asset)
    asset = record_replay(store.load(asset["asset_id"]), passed=True,
                          original_result={"ok": True}, replay_result={"ok": True},
                          evidence=["replay.json"])
    store.save(asset)
    for state in ("human_verified", "approved", "healthy"):
        store.promote(asset["asset_id"], state, evidence=["capture.json"])
    assert store.executable(asset["asset_id"])
    assert store.list(state="healthy")[0]["asset_id"] == asset["asset_id"]


def test_visual_baseline_store_records_hash_and_approval(tmp_path: Path):
    image = tmp_path / "screen.png"
    Image.new("RGBA", (2, 2), "white").save(image)
    store = VisualBaselineStore(tmp_path / "baselines")
    metadata = store.record("login-card", image, approver="qa")
    assert metadata["approved"] is True
    loaded = store.get("login-card")
    assert Path(loaded["path"]).is_file()
