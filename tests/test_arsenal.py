import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

from core.arsenal import (CapabilityState, ObjectRecord, StepState, claim_object,
                          load_capabilities, plan_dependencies)


def _capabilities(tmp_path):
    path = tmp_path / "capabilities.yaml"
    path.write_text(yaml.safe_dump({"capabilities": [
        {"capability_id": "object.create", "version": "1.0.0", "kind": "create",
         "environment": "test", "state": "healthy", "provides": {"object": "item", "state": "draft"},
         "effects": {"mutates": True}, "compensation": {"capability": "object.cancel"}},
        {"capability_id": "object.verify", "version": "1.0.0", "kind": "verify",
         "environment": "test", "state": "healthy", "provides": {"object": "item", "state": "approved"}},
    ]}), encoding="utf-8")
    return load_capabilities(path)


def test_plan_is_hashed_and_compensates_reverse_order(tmp_path):
    capabilities = _capabilities(tmp_path)
    plan = plan_dependencies({"case_id": "case-1", "preconditions": [
        {"capability": "object.create"}], "action": {"capability": "object.verify"}},
        capabilities, environment="test", run_id="run-1")
    assert plan.plan_hash and plan.dependency_hash
    assert plan.steps[0]["state"] == StepState.NOT_STARTED.value
    assert plan.approval_required is True
    assert plan.compensation_steps[0]["for_step"] == "S1"


def test_unhealthy_capability_cannot_be_selected(tmp_path):
    capabilities = _capabilities(tmp_path)
    capabilities[0] = capabilities[0].__class__(**{**capabilities[0].__dict__, "state": CapabilityState.UNHEALTHY})
    try:
        plan_dependencies({"case_id": "case-1", "action": {"capability": "object.create"}},
                          capabilities, environment="test", run_id="run-1")
    except ValueError as exc:
        assert "no healthy capability" in str(exc)
    else:
        raise AssertionError("unhealthy capability must not be selected")


def test_object_claim_prevents_conflicting_lease():
    record = ObjectRecord("item", {"id": "1"}, "draft")
    lease = claim_object(record, run_id="r1", lease_id="l1", now=100)
    assert lease.valid(100)
    try:
        claim_object(record, run_id="r2", lease_id="l2", now=100)
    except RuntimeError:
        pass
    else:
        raise AssertionError("conflicting lease must be rejected")


if __name__ == "__main__":
    import tempfile
    from pathlib import Path
    from pytest import MonkeyPatch
    # The custom runner executes test files directly; use pytest for tmp_path semantics.
    raise SystemExit(__import__("pytest").main([__file__, "-q"]))
