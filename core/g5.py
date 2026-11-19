"""Local 1+2+3+4+5 cumulative delivery acceptance."""
from __future__ import annotations

from pathlib import Path

from .g4 import run_g4
from .lineage import Lineage
from .mock_delivery import MockDeliveryStore, build_delivery_pack
from .mock_requirement import MockRequirementStore, build_pack as build_requirement_pack
from .mock_strategy import MockStrategyStore, build_strategy_pack
from .oracle import evaluate


def run_g5(root: str | Path, *, marker: str = "G5-LOCAL", inject_fault: str = "") -> dict:
    root = Path(root)
    requirements = MockRequirementStore(root / "requirements.sqlite")
    strategies = MockStrategyStore(root / "strategies.sqlite")
    delivery_store = MockDeliveryStore(root / "delivery.sqlite")
    req = build_requirement_pack(requirements)
    strategy = build_strategy_pack(strategies)
    delivery = build_delivery_pack(delivery_store)
    context = {"marker": marker}
    lineage = Lineage()
    try:
        for capability, inputs in (("requirement.create", {"amount": 100000, "department": "TEST-DEPARTMENT"}),
                                   ("requirement.submit", {}), ("requirement.approve", {})):
            result = req.execute(capability, inputs=inputs, context=context)
            context.update(result.get("outputs") or {})
            lineage.capture(result.get("outputs") or {}, capability=capability,
                            parent_variables=("requirement.id",) if capability != "requirement.create" else ())
        for capability, inputs in (("strategy.publish", {"name": "AUTO-G5"}),
                                   ("sourcing.publish", {}),
                                   ("contract.sign", {"amount": 100000}),
                                   ("order.create", {"quantity": 2, "amount": 100000})):
            pack = strategy if capability == "strategy.publish" else delivery
            result = pack.execute(capability, inputs=inputs, context=context)
            context.update(result.get("outputs") or {})
            lineage.capture(result.get("outputs") or {}, capability=capability,
                            parent_variables=("requirement.id", "strategy.id"))
            if inject_fault == capability:
                raise RuntimeError(f"injected fault: {capability}")
        oracle = evaluate([
            {"id": "sourcing-strategy", "subject": "db.strategy_id", "operator": "equals", "expected": context["strategy.id"], "proof": "db"},
            {"id": "contract-sourcing", "subject": "db.sourcing_id", "operator": "equals", "expected": context["sourcing.id"], "proof": "db"},
            {"id": "order-contract", "subject": "db.contract_id", "operator": "equals", "expected": context["contract.id"], "proof": "db"},
            {"id": "order-state", "subject": "api.data.state", "operator": "equals", "expected": "CREATED", "proof": "api"},
        ], {"api": {"data": context["order"]}, "db": {
            "strategy_id": context["sourcing.strategy_id"],
            "sourcing_id": context["contract.sourcing_id"],
            "contract_id": context["order.contract_id"],
        }})
        compensation = delivery.compensate("order.create", context=context)
        compensation_ok = compensation.get("status") == "compensated"
        compensation_ok = compensation_ok and strategy.compensate("strategy.publish", context=context).get("status") == "compensated"
        compensation_ok = compensation_ok and req.compensate("requirement.create", context=context).get("status") == "compensated"
        residue = requirements.residue(marker) + strategies.residue(marker) + delivery_store.residue(marker)
        return {"gate": "G5", "verification_level": "local_e2e", "passed": oracle["passed"] and compensation_ok and residue == 0,
                "oracle": oracle, "compensation": compensation, "residue": residue,
                "lineage": lineage.export(), "context": context}
    except Exception as exc:
        compensation = delivery.compensate("order.create", context=context)
        compensation_ok = compensation.get("status") == "compensated"
        compensation_ok = compensation_ok and strategy.compensate("strategy.publish", context=context).get("status") == "compensated"
        compensation_ok = compensation_ok and req.compensate("requirement.create", context=context).get("status") == "compensated"
        residue = requirements.residue(marker) + strategies.residue(marker) + delivery_store.residue(marker)
        return {"gate": "G5", "verification_level": "local_e2e", "passed": False,
                "fault": str(exc), "recovered": compensation_ok and residue == 0,
                "residue": residue, "lineage": lineage.export(), "context": context}
    finally:
        delivery_store.close(); strategies.close(); requirements.close()
