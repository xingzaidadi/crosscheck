from core.asset_pipeline import can_execute, create_candidate, record_replay, promote
from core.binding_candidates import candidate_executable, generate_binding_candidate
from core.case_identity import compatible_identity, semantic_signature
from core.cross_layer_diagnostics import compare_fields, diagnose_count_mismatch
from core.external_adapters import adapter_readiness
from core.object_lifecycle import ObjectNeed, plan_object_lifecycle
from core.arsenal import ObjectRecord


def test_binding_candidate_requires_review_and_preserves_identity():
    case = {"case_id": "TC1", "title": "Create item", "module": "items", "steps": "POST item"}
    candidate = generate_binding_candidate(
        case,
        [{"method": "POST", "path": "/api/item", "body": {"name": "{{name}}"}}],
        suite_fingerprint="suite-a",
        minimum_confidence=0.2,
    )
    assert candidate["execution"]["request"]["url"] == "/api/item"
    assert not candidate_executable(candidate)
    candidate["state"] = "approved"
    assert candidate_executable(candidate)
    assert compatible_identity(case, candidate, suite_fingerprint="suite-a")[0]
    changed = {**case, "title": "Delete item"}
    assert not compatible_identity(changed, candidate, suite_fingerprint="suite-a")[0]


def test_object_lifecycle_reuses_or_plans_create_and_cleanup():
    existing = [ObjectRecord("item", {"id": "1"}, "ready", {"tenant": "a"})]
    reused = plan_object_lifecycle(ObjectNeed("item", "ready", {"tenant": "a"}), existing,
                                   run_id="r", lease_id="l", now=1)
    assert reused["action"] == "reuse"
    created = plan_object_lifecycle(
        ObjectNeed("item", "draft", {"tenant": "a"}, create_capability="item.create",
                   cleanup_capability="item.delete"), [], run_id="r", lease_id="l2", now=1,
    )
    assert created["action"] == "create_if_missing"
    assert created["cleanup"]["capability"] == "item.delete"


def test_replay_drift_and_cross_layer_diagnostics():
    asset = create_candidate({"action": "click"})
    asset = record_replay(asset, passed=True, original_result={"ok": 1}, replay_result={"ok": 1})
    for state in ("human_verified", "approved", "healthy"):
        asset = promote(asset, state, evidence=["evidence.json"])
    assert can_execute(asset)
    count = diagnose_count_mismatch(10, 5)
    assert count["verdict"] == "INCONCLUSIVE" and "tenant_scope" in count["hypotheses"]
    fields = compare_fields({"status": "Approved"}, {"status": "A"},
                            transforms={"status": {"A": "Approved"}})
    assert fields["matched"]


def test_external_adapter_readiness_is_explicit():
    class Adapter:
        def upload(self):
            pass

    result = adapter_readiness(Adapter(), ["upload", "download"])
    assert result == {"ready": False, "missing_methods": ["download"], "verification_level": "contract"}
