import pytest

from core.asset_store import AssetStore
from core.exploration_promotion import apply_exploration_asset


def test_unreviewed_exploration_asset_cannot_modify_binding(tmp_path):
    workspace = tmp_path / "workspace"
    suite = workspace / "suites" / "demo"
    (suite / "ui_bindings").mkdir(parents=True)
    (suite / "ui_bindings" / "TC1.yaml").write_text(
        "case_id: TC1\nmode: ui\nverify_status: human_verified\nui:\n  page_url: /list\n",
        encoding="utf-8",
    )
    store = AssetStore(workspace / "knowledge_base" / "asset_candidates")
    asset = {"asset_id": "asset-1", "state": "candidate", "payload": {}, "evidence": [],
             "source": {"case_id": "demo/TC1-1", "assertion_id": "TC1:expected:1"}}
    store.save(asset)
    with pytest.raises(ValueError, match="human_verified"):
        apply_exploration_asset("asset-1", workspace=workspace, suite=suite, proof_ref="ui.extract")


def test_reviewed_exploration_asset_binds_assertion(tmp_path):
    workspace = tmp_path / "workspace"
    suite = workspace / "suites" / "demo"
    (suite / "ui_bindings").mkdir(parents=True)
    binding = suite / "ui_bindings" / "TC1.yaml"
    binding.write_text(
        "case_id: TC1\nmode: ui\nverify_status: human_verified\nui:\n  page_url: /list\n",
        encoding="utf-8",
    )
    store = AssetStore(workspace / "knowledge_base" / "asset_candidates")
    store.save({"asset_id": "asset-1", "state": "human_verified", "payload": {},
                "evidence": ["shot.png"],
                "source": {"case_id": "demo/TC1-1", "assertion_id": "TC1:expected:1"}})
    result = apply_exploration_asset(
        "asset-1", workspace=workspace, suite=suite, proof_ref="ui.extract"
    )
    assert result["assertion_id"] == "TC1:expected:1"
    assert "asset-1" in binding.read_text(encoding="utf-8")
