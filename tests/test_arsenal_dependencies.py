import pytest

from core.arsenal import Capability, plan_dependencies


def test_dependency_plan_expands_recursive_capabilities():
    caps = [
        Capability("root", "1", "api", {}, requires={"capabilities": ["child"]}, environment="test"),
        Capability("child", "1", "api", {}, environment="test"),
    ]
    plan = plan_dependencies({"case_id": "c", "action": {"capability": "root"}}, caps,
                             environment="test", run_id="r")
    assert [step["capability"] for step in plan.steps] == ["child@1", "root@1"]


def test_dependency_plan_rejects_conflicting_locks():
    caps = [Capability("a", "1", "api", {}, effects={"conflicts": ["same"]}, environment="test"),
            Capability("b", "1", "api", {}, effects={"conflicts": ["same"]}, environment="test")]
    with pytest.raises(ValueError, match="conflict"):
        plan_dependencies({"case_id": "c", "action": {"capability": "a"},
                           "preconditions": [{"capability": "b"}]}, caps,
                          environment="test", run_id="r")


def test_dependency_plan_orders_dependencies_before_root():
    caps = [Capability("root", "1", "api", {}, requires={"capabilities": ["child"]}, environment="test"),
            Capability("child", "1", "api", {}, requires={"capabilities": ["leaf"]}, environment="test"),
            Capability("leaf", "1", "api", {}, environment="test")]
    plan = plan_dependencies({"case_id": "c", "action": {"capability": "root"}}, caps,
                             environment="test", run_id="r")
    assert [step["capability"] for step in plan.steps] == ["leaf@1", "child@1", "root@1"]


def test_dependency_plan_rejects_cycles():
    caps = [Capability("a", "1", "api", {}, requires={"capabilities": ["b"]}, environment="test"),
            Capability("b", "1", "api", {}, requires={"capabilities": ["a"]}, environment="test")]
    with pytest.raises(ValueError, match="cycle"):
        plan_dependencies({"case_id": "c", "action": {"capability": "a"}}, caps,
                          environment="test", run_id="r")
