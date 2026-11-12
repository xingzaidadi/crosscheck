"""Pilot/batch runner resumes and stops on cleanup/environment safety failures."""
from __future__ import annotations

import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.interfaces import CaseResult, Verdict  # noqa: E402
from core.pipeline_runner import run_pipeline  # noqa: E402


def main() -> None:
    specs = [SimpleNamespace(case_id=f"C{i}", mode="reconcile") for i in range(4)]
    with tempfile.TemporaryDirectory() as directory:
        seen = []
        out = run_pipeline(specs, lambda spec: seen.append(spec.case_id) or CaseResult(spec.case_id, Verdict.PASS),
                           directory, pilot_size=1)
        assert not out.stopped and len(seen) == 4
        seen2 = []
        out2 = run_pipeline(specs, lambda spec: seen2.append(spec.case_id) or CaseResult(spec.case_id, Verdict.PASS),
                            directory, pilot_size=1)
        assert not seen2 and len(out2.results) == 4
        try:
            run_pipeline(specs + [SimpleNamespace(case_id="new", mode="reconcile")],
                         lambda spec: CaseResult(spec.case_id, Verdict.PASS), directory)
        except RuntimeError as exc:
            assert "plan changed" in str(exc)
        else:
            raise AssertionError("changed plan must not reuse checkpoint")

    with tempfile.TemporaryDirectory() as directory:
        calls = 0
        def env(spec):
            nonlocal calls
            calls += 1
            return CaseResult(spec.case_id, Verdict.ENV_ERROR)
        out = run_pipeline(specs, env, directory, pilot_size=0, env_error_limit=3)
        assert out.stopped and calls == 6 and "circuit breaker" in out.reason

    with tempfile.TemporaryDirectory() as directory:
        out = run_pipeline(specs, lambda spec: CaseResult(spec.case_id, Verdict.PASS, cleanup_ok=False),
                           directory, pilot_size=1)
        assert out.stopped and "cleanup failed" in out.reason
    with tempfile.TemporaryDirectory() as directory:
        write_calls = []
        write = SimpleNamespace(case_id="write", mode="api")
        run_pipeline([write], lambda spec: write_calls.append(spec.case_id) or CaseResult(spec.case_id, Verdict.ENV_ERROR),
                     directory, pilot_size=1)
        assert len(write_calls) == 1, "write operations must never be blindly retried"
    print("pipeline runner passed")


if __name__ == "__main__":
    main()
