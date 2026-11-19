from pathlib import Path

from core.g4 import run_g4


def test_requirement_to_strategy_g4_has_lineage_and_cleanup(tmp_path: Path):
    result = run_g4(tmp_path)
    assert result["passed"] is True
    assert result["residue"] == 0
    assert any(item["variable"] == "requirement.id" for item in result["lineage"])
    assert any(item["variable"] == "strategy.id" for item in result["lineage"])
