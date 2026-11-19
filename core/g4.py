"""Local G4 cumulative requirement -> strategy acceptance."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .lineage import Lineage
from .mock_requirement import MockRequirementStore, build_pack as build_requirement_pack
from .mock_strategy import MockStrategyStore, build_strategy_pack
from .oracle import evaluate


def run_g4(root: str | Path, *, marker: str = "G4-LOCAL") -> dict[str, Any]:
    root = Path(root)
    requirement_store = MockRequirementStore(root / "requirements.sqlite")
    strategy_store = MockStrategyStore(root / "strategies.sqlite")
    requirement = build_requirement_pack(requirement_store)
    strategy = build_strategy_pack(strategy_store)
    lineage = Lineage()
    context: dict[str, Any] = {"marker": marker}
    try:
        created = requirement.execute("requirement.create", inputs={"amount": 100000, "department": "TEST-DEPARTMENT"}, context=context)
        context.update(created["outputs"]); lineage.capture(created["outputs"], capability="requirement.create")
        for capability in ("requirement.submit", "requirement.approve"):
            result = requirement.execute(capability, context=context)
            context.update(result["outputs"]); lineage.capture(result["outputs"], capability=capability,
                                                               parent_variables=("requirement.id",))
        published = strategy.execute("strategy.publish", inputs={"name": "AUTO-G4"}, context=context)
        context.update(published["outputs"]); lineage.capture(published["outputs"], capability="strategy.publish",
                                                               parent_variables=("requirement.id",))
        evidence = {"api": published["evidence"]["api"], "db": published["evidence"]["db"]}
        oracle = evaluate([
            {"id": "strategy-status", "subject": "api.data.state", "operator": "equals", "expected": "PUBLISHED", "proof": "api"},
            {"id": "strategy-requirement", "subject": "db.requirement_id", "operator": "equals", "expected": context["requirement.id"], "proof": "db"},
        ], evidence)
        compensation = strategy.compensate("strategy.publish", context=context)
        requirement_compensation = requirement.compensate("requirement.create", context=context)
        compensation_ok = compensation.get("status") == "compensated"
        compensation_ok = compensation_ok and requirement_compensation.get("status") == "compensated"
        residue = strategy_store.residue(marker) + requirement_store.residue(marker)
        return {"gate": "G4", "verification_level": "local_e2e", "passed": oracle["passed"] and compensation_ok and residue == 0,
                "oracle": oracle, "compensation": {"strategy": compensation, "requirement": requirement_compensation}, "residue": residue,
                "lineage": lineage.export(), "context": context}
    finally:
        strategy_store.close(); requirement_store.close()
