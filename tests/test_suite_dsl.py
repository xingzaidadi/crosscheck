"""Canonical suite DSL validation and scoring."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.suite_dsl import case_content_hash, score_case, score_suite  # noqa: E402


def main() -> None:
    suite = {"schema_version": 1, "suite_id": "demo-suite", "version": "1", "environment": "test"}
    good = {"schema_version": 1, "case_id": "demo-001", "title": "列表一致性", "suite_id": "demo-suite",
            "status": "ready", "layers": {"required": ["ui", "api", "db"]},
            "data": {"fixtures": [{"recipe": "list"}]},
            "actions": {"ui": [{"open": {"path": "/list"}}]},
            "assertions": {"ui": [{"id": "A-UI", "visible": {"text": "A"}}],
                           "api": [{"id": "A-API", "response": {"path": "code", "equals": 200}}],
                           "db": [{"id": "A-DB", "row_count": {"table": "items", "equals": 1}}]},
            "cleanup": {"strategy": "marker", "targets": [{"table": "items"}]}}
    good["execution"] = {"mode": "ui", "ui": {"url_pattern": "/api/list"}, "db": "demo",
                         "feature": "列表", "assertion_bindings": {
                             "A-UI": {"layer": "ui", "proof": "ui_check", "ref": "ui.extract"},
                             "A-API": {"layer": "api", "proof": "api_response", "ref": "engine_assertions.response"},
                             "A-DB": {"layer": "db", "proof": "db_assertion", "ref": "engine_assertions.db[0]"}}}
    good["approval"] = {"status": "human_verified", "content_hash": case_content_hash(good)}
    assert score_case(good)["execution_ready"]
    bad = dict(good, suite_id="other-suite")
    assert not score_case(bad, "demo-suite")["execution_ready"]
    result = score_suite(suite, [good])
    assert result["execution_ready"] == 1 and result["average_score"] >= 90
    print("suite DSL passed")


if __name__ == "__main__":
    main()
