"""Evaluate a frozen feature acceptance manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.feature_gate import FeatureGate, evaluate
from core.manifest import verify_manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    results = json.loads(args.results.read_text(encoding="utf-8"))
    manifest_errors = verify_manifest(manifest)
    gate = FeatureGate(str(manifest["feature_id"]), tuple(manifest.get("required_cases") or []),
                       bool(manifest.get("require_soak")), bool(manifest.get("require_fault_injection")),
                       bool(manifest.get("require_zero_residue", True)))
    output = evaluate(gate, results, soak_passed=bool(manifest.get("soak_passed")),
                      fault_injection_passed=bool(manifest.get("fault_injection_passed")),
                      residue_count=int(manifest.get("residue_count", 0)))
    output["manifest_errors"] = manifest_errors
    if manifest_errors:
        output["done"] = False
        output["reasons"] = list(output.get("reasons") or []) + ["invalid_manifest"]
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["done"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
