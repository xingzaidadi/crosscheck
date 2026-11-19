import json

from core.local_delivery_acceptance import run_local_delivery_acceptance


def test_unified_local_delivery_artifact(tmp_path):
    output = tmp_path / "local-acceptance.json"
    result = run_local_delivery_acceptance(repetitions=2, output=output)
    assert result["passed"] is True
    assert result["gates"]["G5"] is True
    assert result["manifest"]["manifest_hash"]
    assert result["artifact_hash"]
    assert json.loads(output.read_text(encoding="utf-8"))["passed"] is True
