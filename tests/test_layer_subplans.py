from core.layer_subplans import LayerSubplan, execute_subplans
from core.layered_execution import LayerResult, LayerVerdict


def test_subplans_retry_environment_error_and_keep_checkpoint():
    calls = []

    def api(context):
        calls.append(context["checkpoint"])
        if len(calls) == 1:
            return LayerResult("api", LayerVerdict.ENV_ERROR, checkpoint="api:request")
        return LayerResult("api", LayerVerdict.PASS, evidence=["api.json"], checkpoint="api:done")

    report = execute_subplans(
        [LayerSubplan("api", max_attempts=2, checkpoint="api:start")],
        {"api": api},
    )

    assert report["verdict"] == "PASS"
    assert report["subplans"][0]["attempts"] == 2
    assert report["subplans"][0]["recovered"] is True
    assert report["subplans"][0]["checkpoint"] == "api:done"


def test_cross_fail_is_distinct_from_optional_failure():
    report = execute_subplans(
        [LayerSubplan("ui"), LayerSubplan("api")],
        {
            "ui": lambda _: True,
            "api": lambda _: LayerResult("api", LayerVerdict.FAIL, details=["401"]),
        },
    )

    assert report["verdict"] == "CROSS_FAIL"


def test_missing_runner_is_cross_inconclusive():
    report = execute_subplans(
        [LayerSubplan("ui"), LayerSubplan("db")],
        {"ui": lambda _: True},
    )

    assert report["verdict"] == "CROSS_INCONCLUSIVE"
    assert report["missing_required"] == ["db"]
