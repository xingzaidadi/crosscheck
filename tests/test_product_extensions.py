"""Dashboard, system map, rule binding, and failure learning work offline."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.control_plane import render_dashboard, snapshot  # noqa: E402
from core.knowledge import KnowledgeBase  # noqa: E402
from core.system_map import write_system_map  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory) / "workspace"
        for path in (workspace / "profiles", workspace / "suites" / "demo", workspace / "runs",
                     workspace / "knowledge_base" / "api_catalog", workspace / "knowledge_base" / "schema_map"):
            path.mkdir(parents=True, exist_ok=True)
        (workspace / "profiles" / "demo.yaml").write_text("site: demo\n", encoding="utf-8")
        (workspace / "knowledge_base" / "api_catalog" / "demo.json").write_text('{"endpoints": []}', encoding="utf-8")
        knowledge = KnowledgeBase(workspace).load()
        record = {
            "knowledge_id": "K-RULE-001", "type": "business_rule", "scope": {},
            "statement": {"natural_language": "列表接口返回成功"},
            "compiled": {
                "assertions": {"api": [{"id": "A-RULE", "response": {"path": "code", "equals": 200}}]},
                "engine_assertions": {"response": {"status": 200}},
                "assertion_bindings": {"A-RULE": {"layer": "api", "proof": "api_response",
                                                      "ref": "engine_assertions.response"}},
            },
            "source": {"type": "manual"},
            "governance": {"approval_status": "approved", "confidence": 0.95},
        }
        knowledge.write_pending(record)
        knowledge = KnowledgeBase(workspace).load()
        case = {"suite_id": "demo", "title": "列表接口返回成功", "source": {}, "execution": {},
                "business_tags": [], "open_questions": [], "assertions": {}}
        bound = knowledge.bind_recommendations(case)
        assert bound["knowledge_refs"] == ["K-RULE-001"]
        assert bound["assertions"]["api"][0]["id"] == "A-RULE"
        failure_path = knowledge.learn_failure(case_id="C1", category="env_error", details=["network timeout"])
        assert failure_path.is_file()
        dashboard = render_dashboard(workspace)
        assert dashboard.is_file() and snapshot(workspace)["knowledge"]["total"] >= 2
        system_map = write_system_map(workspace)
        data = json.loads(system_map.read_text(encoding="utf-8"))
        assert "ui" in data and "api" in data and "database" in data
    print("product extensions passed")


if __name__ == "__main__":
    main()
