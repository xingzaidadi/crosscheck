"""Suite-local connector binding and connector approval drift prevention."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.suite_bindings import resolve_bindings
from core.suite_compiler import compile_case
from core.suite_context import SuiteContext
from core.suite_dsl import case_content_hash, source_hash


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory)
        root = workspace / "suites" / "demo"
        root.mkdir(parents=True)
        (root / "suite.yaml").write_text("suite_id: demo\n", encoding="utf-8")
        context = SuiteContext.create(root, workspace)
        connector = {"suite_id": "demo", "actions": {"query": {
            "mode": "reconcile", "request": {"method": "GET", "url": "/api/items"},
            "engine_assertions": {"response": {"status": 200}}}}}
        (root / "connector.yaml").write_text(yaml.safe_dump(connector), encoding="utf-8")
        suite = {"suite_id": "demo", "connector": "connector.yaml"}
        case = {"schema_version": 1, "case_id": "demo/query", "title": "query", "suite_id": "demo",
                "status": "ready", "layers": {"required": ["api"]},
                "actions": {"api": [{"get": "/api/items"}]},
                "assertions": {"api": [{"id": "A1", "response": {"path": "code", "equals": 200}}]},
                "cleanup": {"strategy": "none", "targets": []},
                "execution": {"action_ref": "query", "assertion_bindings": {"A1": {
                    "layer": "api", "proof": "api_response", "ref": "engine_assertions.response"}}}}
        case["approval"] = {"status": "human_verified", "content_hash": case_content_hash(case),
                            "connector_hash": source_hash(connector)}
        resolved = resolve_bindings(case, suite, context)
        assert resolved["execution"]["request"]["url"] == "/api/items"
        compile_case(case, suite, context)
        connector["actions"]["query"]["request"]["url"] = "/api/other"
        (root / "connector.yaml").write_text(yaml.safe_dump(connector), encoding="utf-8")
        try:
            compile_case(case, suite, context)
        except ValueError as exc:
            assert "connector" in str(exc)
        else:
            raise AssertionError("changed connector must invalidate approval")
    print("suite connector binding passed")


if __name__ == "__main__":
    main()
