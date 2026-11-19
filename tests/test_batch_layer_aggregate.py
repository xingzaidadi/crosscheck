from types import SimpleNamespace

from run_batch import _attach_layer_aggregate


def test_batch_attaches_inconclusive_layer_aggregate():
    result = SimpleNamespace(verdict=__import__("core.interfaces", fromlist=["Verdict"]).Verdict.PASS,
                             report={"layers": [{"name": "UI", "ok": True}, {"name": "API", "ok": None}]})
    _attach_layer_aggregate(result)
    assert result.report["layer_aggregate"]["verdict"] == "INCONCLUSIVE"
