from pathlib import Path

from core.mock_requirement import MockRequirementStore, build_pack
from core.soak import run_soak
from core.local_case_runner import run_case


def test_mock_requirement_lifecycle_and_compensation(tmp_path: Path):
    store = MockRequirementStore(tmp_path / "requirements.sqlite")
    pack = build_pack(store)
    context = {"marker": "M-1"}
    created = pack.execute("requirement.create", inputs={"amount": 10, "department": "采购"}, context=context)
    context.update(created["outputs"])
    assert context["requirement"]["state"] == "DRAFT"
    for capability in ("requirement.submit", "requirement.approve", "requirement.verify"):
        context.update(pack.execute(capability, inputs={}, context=context)["outputs"])
    assert context["requirement.state"] == "VERIFIED"
    pack.compensate("requirement.create", context=context)
    assert store.residue("M-1") == 0
    store.close()


def test_mock_requirement_five_run_soak(tmp_path: Path):
    def one(index):
        store = MockRequirementStore(tmp_path / f"run-{index}.sqlite")
        pack = build_pack(store)
        context = {"marker": f"M-{index}"}
        created = pack.execute("requirement.create", inputs={"amount": index, "department": "采购"}, context=context)
        context.update(created["outputs"])
        pack.compensate("requirement.create", context=context)
        residue = store.residue(f"M-{index}")
        store.close()
        return {"passed": residue == 0, "residue": residue}
    assert run_soak(one, repetitions=5)["passed"]


def test_requirement_case_v2_runs_through_layered_local_runner(tmp_path: Path):
    store = MockRequirementStore(tmp_path / "requirements.sqlite")
    case = {"schema_version": 2, "case_id": "REQ-CASE-1", "title": "创建需求",
            "traceability": {"requirements": ["R1"]}, "intent": {"under_test": "requirement.create"},
            "preconditions": [], "action": {"capability": "requirement.create",
                                               "inputs": {"amount": 10, "department": "采购", "marker": "C1"}},
            "actors": {"operator": {"role": "creator"}},
            "oracles": [{"id": "api", "subject": "api.status", "operator": "equals", "expected": 201, "proof": "api"},
                        {"id": "db", "subject": "db.state", "operator": "equals", "expected": "DRAFT", "proof": "db"}],
            "layers": {"required": ["api", "db"]}}
    result = run_case(case, build_pack(store))
    assert result["verdict"] == "PASS"
    assert result["layer_aggregate"]["verdict"] == "PASS"
    store.close()
