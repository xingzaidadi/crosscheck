"""Two unrelated domains compile through canonical contracts without core changes."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.suite_compiler import compile_case  # noqa: E402
from core.suite_context import SuiteContext  # noqa: E402
from core.suite_dsl import case_content_hash  # noqa: E402


def canonical(suite_id: str, case_id: str, title: str, table: str, endpoint: str) -> dict:
    case = {
        "schema_version": 1, "case_id": f"{suite_id}/{case_id}", "title": title, "suite_id": suite_id,
        "status": "ready", "priority": "P0", "scenario_type": "write",
        "source": {"case_key": case_id}, "layers": {"required": ["api", "db"]},
        "data": {"fixtures": [{"name": "payload"}]}, "actions": {"api": [{"post": endpoint}]},
        "assertions": {"api": [{"id": "API-1", "response": {"path": "code", "equals": 200}}],
                       "db": [{"id": "DB-1", "row_count": {"table": table, "equals": 1}}]},
        "cleanup": {"strategy": "marker", "targets": [{"table": table, "column": "name"}]},
        "evidence": {"required": ["api_response", "db_result"]},
        "execution": {"mode": "api", "db": f"{suite_id}-db", "request": {"method": "POST", "url": endpoint, "body": {}},
                      "engine_assertions": {"response": {"status": 200}, "db": [{"table": table, "where": "name='{{marker}}'", "row_count": 1}]},
                      "cleanup": [{"table": table, "column": "name"}], "allowed_tables": [table],
                      "assertion_bindings": {"API-1": {"layer": "api", "proof": "api_response", "ref": "engine_assertions.response"},
                                             "DB-1": {"layer": "db", "proof": "db_assertion", "ref": "engine_assertions.db[0]"}}},
    }
    case["approval"] = {"status": "human_verified", "content_hash": case_content_hash(case)}
    return case


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory) / "workspace"
        domains = [
            ("procurement", canonical("procurement", "create-demand", "创建采购需求", "demand_request", "/api/demand")),
            ("library", canonical("library", "create-book", "新增图书", "book", "/api/book")),
        ]
        specs = []
        for suite_id, case in domains:
            suite_dir = workspace / "suites" / suite_id
            suite_dir.mkdir(parents=True)
            (suite_dir / "suite.yaml").write_text(f"suite_id: {suite_id}\n", encoding="utf-8")
            context = SuiteContext.create(suite_dir, workspace)
            specs.append(compile_case(case, {"suite_id": suite_id}, context))
        assert specs[0].request["url"] == "/api/demand"
        assert specs[1].request["url"] == "/api/book"
        assert specs[0].raw["suite_id"] != specs[1].raw["suite_id"]
    print("cross-domain canonical compile passed")


if __name__ == "__main__":
    main()
