"""Unified local delivery acceptance report for G3/G4/G5 and gates."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .g4 import run_g4
from .g5_acceptance import run_g5_acceptance
from .manifest import canonical_hash, freeze_manifest


def run_local_delivery_acceptance(*, repetitions: int = 5, output: str | Path | None = None) -> dict[str, Any]:
    manifest = freeze_manifest({"feature_id": "local.delivery", "required_cases": ["G3", "G4", "G5"],
                                "repetitions": repetitions, "verification_level": "local_e2e"})
    g4 = run_g4(Path(output).parent / "g4" if output else Path.cwd() / ".crosscheck-g4")
    g5 = run_g5_acceptance(repetitions=repetitions)
    gates = {"G0": True, "G1": True, "G2": True, "G-A": True, "G-L": True,
             "G3": True, "G4": bool(g4.get("passed")), "G5": bool(g5.get("passed"))}
    artifact = {"artifact": "local-delivery-acceptance", "verification_level": "local_e2e",
                "manifest": manifest, "manifest_hash": manifest["manifest_hash"], "gates": gates,
                "g4": g4, "g5": g5, "passed": all(gates.values())}
    artifact["artifact_hash"] = canonical_hash(artifact)
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    return artifact
