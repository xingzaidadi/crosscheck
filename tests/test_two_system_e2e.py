"""Two unrelated systems compile and produce isolated executable plans."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.suite_compiler import compile_suite, write_plan  # noqa: E402
from core.suite_context import SuiteContext  # noqa: E402
from core.suite_dsl import case_content_hash  # noqa: E402


def build_case(suite_id: str, endpoint: str, table: str) -> dict:
    case = {
        "schema_version": 1, "case_id": f"{suite_id}/query", "title": f"{suite_id} list",
        "suite_id": suite_id, "status": "ready", "priority": "P0", "scenario_type": "query",
        "source": {"case_key": "Q1"}, "layers": {"required": ["api", "db"]},
        "data": {"fixtures": [{"name": "existing"}]}, "actions": {"api": [{"get": endpoint}]},
        "assertions": {"api": [{"id": "A1"}], "db": [{"id": "D1"}]},
        "cleanup": {"strategy": "marker", "targets": [{"table": table, "column": "name"}]},
        "evidence": {"required": ["api_response", "db_result"]},
        "execution": {"mode": "reconcile", "request": {"url": endpoint},
                      "engine_assertions": {"response": {"status": 200},
                                            "db": [{"table": table, "where": "1=1", "row_count": 1}]},
                      "assertion_bindings": {
                          "A1": {"layer": "api", "proof": "api_response", "ref": "engine_assertions.response"},
                          "D1": {"layer": "db", "proof": "db_assertion", "ref": "engine_assertions.db[0]"}}},
    }
    case["approval"] = {"status": "human_verified", "content_hash": case_content_hash(case)}
    return case


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory) / "workspace"
        plans = []
        for suite_id, endpoint, table in (("inventory", "/api/stock", "stock_item"),
                                          ("billing", "/api/invoices", "invoice")):
            suite_dir = workspace / "suites" / suite_id
            suite_dir.mkdir(parents=True)
            suite = {"schema_version": 1, "suite_id": suite_id, "environment": "test"}
            (suite_dir / "suite.yaml").write_text(yaml.safe_dump(suite), encoding="utf-8")
            specs, invalid = compile_suite(suite, [build_case(suite_id, endpoint, table)],
                                           SuiteContext.create(suite_dir, workspace))
            assert not invalid and len(specs) == 1
            plans.append(write_plan(specs, suite_dir / "reports" / "execution_plan.json"))
        assert plans[0].read_text(encoding="utf-8") != plans[1].read_text(encoding="utf-8")
    print("two-system E2E passed")


if __name__ == "__main__":
    main()
