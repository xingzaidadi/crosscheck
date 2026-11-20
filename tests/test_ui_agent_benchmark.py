from core.ui_agent.benchmark import run_benchmark


def test_real_browser_benchmark_passes_ninety_percent(tmp_path):
    report = run_benchmark(tmp_path / "benchmark", repetitions=5)
    assert report["maturity"]["status"] == "PASSED"
    assert report["maturity"]["score"] >= 90
    assert all(item["execution"]["observations"] for item in report["samples"])
