import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.run_registry import RunRegistry  # noqa: E402


def test_registry_persists_steps_and_unknown_recovery(tmp_path):
    registry = RunRegistry(tmp_path / "registry.sqlite3")
    registry.create_run("run-1", "plan-1", "test")
    registry.register_object("object-1", "item", {"id": "1"}, "draft")
    registry.claim_lease("object-1", "lease-1", "run-1", ttl_s=60)
    registry.save_step("run-1", "S1", "object.create@1.0.0", "unknown", "timeout")
    assert registry.recoverable_steps("run-1")[0]["state"] == "unknown"
    events = registry.audit_events("run-1")
    assert [event["event_type"] for event in events] == ["run_created", "lease_claimed", "step_state"]
    registry.close()


def test_registry_rejects_concurrent_object_lease(tmp_path):
    registry = RunRegistry(tmp_path / "registry.sqlite3")
    registry.create_run("run-1", "plan-1", "test")
    registry.create_run("run-2", "plan-2", "test")
    registry.register_object("object-1", "item", {"id": "1"}, "draft")
    registry.claim_lease("object-1", "lease-1", "run-1")
    try:
        registry.claim_lease("object-1", "lease-2", "run-2")
    except RuntimeError as exc:
        assert "lease conflict" in str(exc)
    else:
        raise AssertionError("second active lease must be rejected")
    registry.close()


if __name__ == "__main__":
    raise SystemExit(__import__("pytest").main([__file__, "-q"]))
