from pathlib import Path

from core.g5 import run_g5


def test_full_local_delivery_chain(tmp_path: Path):
    result = run_g5(tmp_path)
    assert result["passed"] is True
    assert result["residue"] == 0
    variables = {item["variable"] for item in result["lineage"]}
    assert {"requirement.id", "strategy.id", "sourcing.id", "contract.id", "order.id"} <= variables
