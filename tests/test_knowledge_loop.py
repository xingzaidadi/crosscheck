"""User answers persist, prevent repeat questions, and bind approved plans."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.knowledge import KnowledgeBase, question_fingerprint  # noqa: E402
from core.suite_compiler import compile_case  # noqa: E402
from core.suite_context import SuiteContext  # noqa: E402
from core.suite_dsl import case_content_hash  # noqa: E402


def ready_case() -> dict:
    return {
        "schema_version": 1, "case_id": "suite-a/case-1", "title": "列表校验", "suite_id": "suite-a",
        "status": "ready", "priority": "P0", "scenario_type": "query", "source": {"case_key": "TC01"},
        "layers": {"required": ["api"]}, "data": {"fixtures": [{"name": "existing"}]},
        "actions": {"api": [{"get": "/api/items"}]},
        "assertions": {"api": [{"id": "A-API", "response": {"path": "code", "equals": 200}}]},
        "cleanup": {"strategy": "marker", "targets": [{"table": "items", "column": "name"}]},
        "evidence": {"required": ["api_response"]},
        "execution": {
            "mode": "reconcile", "feature": "items", "request": {"url": "/api/items"},
            "engine_assertions": {"response": {"status": 200}},
            "assertion_bindings": {"A-API": {"layer": "api", "proof": "api_response",
                                                        "ref": "engine_assertions.response"}},
        },
    }


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory) / "workspace"
        suite_dir = workspace / "suites" / "suite-a"
        suite_dir.mkdir(parents=True)
        (suite_dir / "suite.yaml").write_text("schema_version: 1\nsuite_id: suite-a\n", encoding="utf-8")
        scope = {"project": "demo", "module": "items"}
        knowledge = KnowledgeBase(workspace).load()
        record = knowledge.record_answer(question="谁可以处理这条记录？", answer="当前办理人",
                                         scope=scope, knowledge_id="K-ROLE-001")
        fingerprint = question_fingerprint(*list(scope.values()), "谁可以处理这条记录？")
        assert knowledge.answer_for(fingerprint, scope=scope) is None
        knowledge.approve(record["knowledge_id"], approver="tester")
        knowledge = KnowledgeBase(workspace).load()
        assert knowledge.answer_for(fingerprint, scope=scope)["statement"]["natural_language"] == "当前办理人"
        recommendations = knowledge.recommend_for_case({
            "suite_id": "demo", "title": "谁可以处理这条记录 当前办理人", "source": {"module": "items"},
            "execution": {}, "business_tags": ["role"], "open_questions": []})
        assert recommendations and recommendations[0]["knowledge_id"] == "K-ROLE-001"
        assert knowledge.question_status("谁可以处理这条记录？", scope=scope)["may_ask"] is False
        try:
            knowledge.require_question("谁可以处理这条记录？", scope=scope)
        except ValueError as exc:
            assert "repeated question blocked" in str(exc)
        else:
            raise AssertionError("approved answers must block repeated questions")

        case = ready_case()
        case["knowledge_refs"] = ["K-ROLE-001"]
        dependency = knowledge.dependency("K-ROLE-001")
        case["approval"] = {"status": "human_verified", "knowledge_hashes": {
            "K-ROLE-001": dependency["content_hash"]}}
        case["approval"]["content_hash"] = case_content_hash(case)
        spec = compile_case(case, {"suite_id": "suite-a"}, SuiteContext.create(suite_dir, workspace))
        assert spec.raw["knowledge_dependencies"][0]["knowledge_id"] == "K-ROLE-001"

        knowledge.capture_run_feedback(["K-ROLE-001"], ok=True, run_id="run-1")
        knowledge = KnowledgeBase(workspace).load()
        assert knowledge.get("K-ROLE-001")["verification"]["success_count"] == 1
        compile_case(case, {"suite_id": "suite-a"}, SuiteContext.create(suite_dir, workspace))

        approved_path = next((workspace / "knowledge_base").rglob("K-ROLE-001.json"))
        text = approved_path.read_text(encoding="utf-8").replace("当前办理人", "当前负责人")
        approved_path.write_text(text, encoding="utf-8")
        try:
            compile_case(case, {"suite_id": "suite-a"}, SuiteContext.create(suite_dir, workspace))
        except ValueError as exc:
            assert "knowledge changed" in str(exc)
        else:
            raise AssertionError("knowledge drift must invalidate approval")

        knowledge = KnowledgeBase(workspace).load()
        conflicting = knowledge.record_answer(question="谁可以处理这条记录？", answer="创建人",
                                               scope=scope, knowledge_id="K-ROLE-002")
        knowledge = KnowledgeBase(workspace).load()
        assert knowledge.get(conflicting["knowledge_id"])["governance"]["conflicted"] is True
        knowledge.supersede("K-ROLE-001", "K-ROLE-002", approver="tester")
        knowledge = KnowledgeBase(workspace).load()
        assert knowledge.get("K-ROLE-001")["governance"]["stale"] is True
        assert knowledge.get("K-ROLE-002", approved_only=True) is not None
    print("knowledge loop passed")


if __name__ == "__main__":
    main()
