from core.case_auditor import audit_case
from core.gates import evaluate_gates
from core.manifest import freeze_manifest, verify_manifest


def test_manifest_freeze_and_tamper_detection():
    manifest = freeze_manifest({"feature_id": "f", "required_cases": ["c1"]})
    assert verify_manifest(manifest) == []
    manifest["required_cases"] = ["c2"]
    assert verify_manifest(manifest)


def test_case_auditor_blocks_missing_role_and_open_questions():
    report = audit_case({"schema_version": 2, "case_id": "c", "title": "创建需求",
                         "traceability": {"requirements": ["R1"]},
                         "intent": {"under_test": "requirement.create"},
                         "preconditions": [], "action": {"capability": "requirement.create"},
                         "oracles": [{"id": "a", "subject": "api.status", "operator": "equals",
                                      "expected": 201, "proof": "api"}],
                         "open_questions": ["角色未确认"]})
    assert report["ready"] is False
    assert any(item["kind"] == "role" for item in report["issues"])


def test_unified_gates_never_pass_without_real_inputs():
    output = evaluate_gates(cases=[], manifest=None, facts={"missing": ["environment"]})
    assert output["passed"] is False
    assert output["gates"]["G0"] is False
