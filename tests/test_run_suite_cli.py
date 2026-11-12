"""run_suite enforces environment authorization and compiles canonical plans end to end."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.suite_dsl import case_content_hash  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory) / "workspace"
        suite_dir = workspace / "suites" / "demo"
        (suite_dir / "cases").mkdir(parents=True)
        suite = {"schema_version": 1, "suite_id": "demo", "environment": "test",
                 "authorization": {"confirmed_non_production": False}}
        (suite_dir / "suite.yaml").write_text(yaml.safe_dump(suite), encoding="utf-8")
        case = {
            "schema_version": 1, "case_id": "demo/query-1", "title": "查询", "suite_id": "demo",
            "status": "ready", "source": {"case_key": "Q1"}, "priority": "P0", "scenario_type": "query",
            "layers": {"required": ["api"]}, "actors": {}, "data": {"fixtures": [{"name": "existing"}]},
            "actions": {"api": [{"get": "/api/items"}]},
            "assertions": {"api": [{"id": "A1", "response": {"path": "code", "equals": 200}}]},
            "cleanup": {"strategy": "marker", "targets": [{"table": "items", "column": "name"}]},
            "evidence": {"required": ["api_response"]},
            "execution": {"mode": "reconcile", "request": {"method": "GET", "url": "/api/items"},
                          "engine_assertions": {"response": {"status": 200}},
                          "assertion_bindings": {"A1": {"layer": "api", "proof": "api_response", "ref": "engine_assertions.response"}}},
        }
        case["approval"] = {"status": "human_verified", "content_hash": case_content_hash(case)}
        (suite_dir / "cases" / "query.yaml").write_text(yaml.safe_dump(case), encoding="utf-8")
        denied = subprocess.run([sys.executable, "run_suite.py", "--suite", str(suite_dir),
                                 "--workspace", str(workspace), "--plan-only"], cwd=ROOT)
        assert denied.returncode == 6, denied.returncode
        suite["authorization"]["confirmed_non_production"] = True
        (suite_dir / "suite.yaml").write_text(yaml.safe_dump(suite), encoding="utf-8")
        allowed = subprocess.run([sys.executable, "run_suite.py", "--suite", str(suite_dir),
                                  "--workspace", str(workspace), "--plan-only"], cwd=ROOT)
        assert allowed.returncode == 0, allowed.returncode
        assert (suite_dir / "reports" / "execution_plan.json").is_file()
    print("run_suite CLI passed")


if __name__ == "__main__":
    main()
