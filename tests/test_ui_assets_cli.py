from core.asset_pipeline import create_candidate, record_replay
from core.asset_store import AssetStore
from scripts.ui_assets import main


def test_ui_assets_can_activate_replayed_asset(tmp_path, monkeypatch, capsys):
    store = AssetStore(tmp_path / "knowledge_base" / "asset_candidates")
    asset = create_candidate({"case_id": "TC1"})
    store.save(record_replay(asset, passed=True, original_result={}, replay_result={}, evidence=["x.png"]))
    monkeypatch.setattr("sys.argv", ["ui-assets", "accept", "--workspace", str(tmp_path),
                                      "--asset-id", asset["asset_id"], "--reviewer", "qa"])
    assert main() == 0
    capsys.readouterr()
    monkeypatch.setattr("sys.argv", ["ui-assets", "activate", "--workspace", str(tmp_path),
                                      "--asset-id", asset["asset_id"], "--reviewer", "lead"])
    assert main() == 0
    assert '"state": "active"' in capsys.readouterr().out
