"""G5 soak, idempotency and fault-injection acceptance artifact."""
from __future__ import annotations

import tempfile
from pathlib import Path

from .g5 import run_g5
from .soak import run_fault_injection, run_soak


def run_g5_acceptance(*, repetitions: int = 5) -> dict:
    with tempfile.TemporaryDirectory(prefix="crosscheck-g5-acceptance-") as directory:
        root = Path(directory)

        def normal(index):
            result = run_g5(root / f"normal-{index}", marker=f"G5-N-{index}")
            return {"passed": result["passed"], "residue": result["residue"]}

        def fault(name):
            result = run_g5(root / f"fault-{name}", marker=f"G5-F-{name}", inject_fault="order.create")
            return {"recovered": result.get("recovered") is True, "residue": result.get("residue")}

        soak = run_soak(normal, repetitions=repetitions)
        faults = run_fault_injection(fault, faults=("timeout", "handler_error"))
        idempotency = run_g5(root / "idempotent", marker="G5-IDEMP")
        return {"gate": "G5", "verification_level": "local_e2e", "passed": soak["passed"] and faults["passed"] and idempotency["passed"],
                "soak": soak, "fault_injection": faults,
                "idempotency": {"passed": idempotency["passed"], "residue": idempotency["residue"]}}
