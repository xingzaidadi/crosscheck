"""Canonical cases compile only with current approval hash and isolated paths."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.suite_compiler import compile_case  # noqa: E402
from core.suite_context import SuiteContext  # noqa: E402
from core.suite_dsl import case_content_hash  # noqa: E402


def ready_case() -> dict:
    case = {
        "schema_version": 1, "case_id": "suite-a/case-1", "title": "列表三层一致", "suite_id": "suite-a",
        "status": "ready", "priority": "P0", "scenario_type": "query",
        "source": {"case_key": "TC01"}, "layers": {"required": ["ui", "api", "db"]},
        "data": {"fixtures": [{"name": "existing"}]},
        "actions": {"ui": [{"open": {"path": "/list"}}]},
        "assertions": {
            "ui": [{"id": "A-UI", "visible": {"text": "item"}}],
            "api": [{"id": "A-API", "response": {"path": "code", "equals": 200}}],
            "db": [{"id": "A-DB", "row_count": {"table": "items", "equals": 1}}],
        },
        "cleanup": {"strategy": "marker", "targets": [{"table": "items", "column": "name"}]},
        "evidence": {"required": ["screenshot", "api_response", "db_result"]},
        "execution": {
            "mode": "ui", "feature": "items", "db": "demo",
            "ui": {"page_url": "/list", "url_pattern": "/api/items", "allow_empty": False,
                   "extract": {"rows_selector": "table tbody tr", "columns": {"name": "td"}}},
            "engine_assertions": {"response": {"status": 200},
                                  "db": [{"table": "items", "where": "name='x'", "row_count": 1}]},
            "assertion_bindings": {"A-UI": {"layer": "ui", "proof": "ui_check", "ref": "ui.extract"},
                                   "A-API": {"layer": "api", "proof": "api_response", "ref": "engine_assertions.response"},
                                   "A-DB": {"layer": "db", "proof": "db_assertion", "ref": "engine_assertions.db[0]"}},
        },
    }
    case["approval"] = {"status": "human_verified", "content_hash": case_content_hash(case)}
    return case


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory) / "workspace"
        suite_dir = workspace / "suites" / "suite-a"
        suite_dir.mkdir(parents=True)
        (suite_dir / "suite.yaml").write_text("suite_id: suite-a\n", encoding="utf-8")
        context = SuiteContext.create(suite_dir, workspace)
        case = ready_case()
        spec = compile_case(case, {"suite_id": "suite-a", "base_url": "https://test.example"}, context)
        assert spec.mode == "ui" and spec.raw["canonical_case_id"] == "suite-a/case-1"
        case["title"] = "changed"
        try:
            compile_case(case, {"suite_id": "suite-a"}, context)
        except ValueError as exc:
            assert "content_hash" in str(exc)
        else:
            raise AssertionError("approval drift must be rejected")
        try:
            context.resolve("../../outside.yaml")
        except ValueError:
            pass
        else:
            raise AssertionError("suite path escape must be rejected")
    print("suite compiler passed")


if __name__ == "__main__":
    main()
