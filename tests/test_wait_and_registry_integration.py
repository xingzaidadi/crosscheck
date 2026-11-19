from types import SimpleNamespace

from core.interfaces import CaseResult, Verdict
from core.pipeline_runner import run_pipeline
from core.run_registry import RunRegistry


def test_pipeline_updates_run_registry(tmp_path):
    registry = RunRegistry(tmp_path / "runs.sqlite")
    spec = SimpleNamespace(case_id="case-1", mode="api", raw={"action_ref": "thing.create"})
    outcome = run_pipeline([spec], lambda _: CaseResult("case-1", Verdict.PASS), tmp_path / "run",
                           pilot_size=1, registry=registry, run_id="run-1", environment="test")
    assert outcome.stopped is False
    assert registry.run("run-1")["status"] == "completed"
    assert registry.steps("run-1")[0]["state"] == "succeeded"
    registry.close()


def test_pipeline_records_unknown_when_executor_raises(tmp_path):
    registry = RunRegistry(tmp_path / "runs.sqlite")
    spec = SimpleNamespace(case_id="case-1", mode="api", raw={"action_ref": "thing.create"})
    outcome = run_pipeline([spec], lambda _: (_ for _ in ()).throw(RuntimeError("timeout")), tmp_path / "run",
                           pilot_size=1, registry=registry, run_id="run-1", environment="test")
    assert outcome.stopped is True
    assert registry.steps("run-1")[0]["state"] == "unknown"
    registry.close()
