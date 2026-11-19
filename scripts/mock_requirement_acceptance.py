"""Run the local requirement capability lifecycle and produce a G3 artifact."""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from core.mock_requirement import MockRequirementStore, build_pack
from core.soak import run_soak


def one_run(root: Path, index: int) -> dict:
    store = MockRequirementStore(root / f"requirement-{index}.sqlite")
    pack = build_pack(store)
    context = {"marker": f"G3-{index}"}
    created = pack.execute("requirement.create", inputs={"amount": 100 + index, "department": "采购"}, context=context)
    context.update(created["outputs"])
    for capability in ("requirement.find", "requirement.submit", "requirement.approve", "requirement.verify"):
        inputs = {"state": "DRAFT"} if capability == "requirement.find" else {}
        found = pack.execute(capability, inputs=inputs, context=context)
        context.update(found["outputs"])
    verified = context["requirement.state"] == "VERIFIED"
    compensated = pack.compensate("requirement.create", context=context)
    residue = store.residue(context["marker"])
    store.close()
    return {"passed": verified and residue == 0 and compensated.get("status") != "manual_required",
            "state": context["requirement.state"], "residue": residue,
            "compensation": compensated}


def main() -> int:
    parser = argparse.ArgumentParser(description="运行本地 requirement G3 验收")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repetitions", type=int, default=5)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="crosscheck-requirement-") as directory:
        root = Path(directory)
        soak = run_soak(lambda index: one_run(root, index), repetitions=args.repetitions)
        artifact = {"gate": "G3", "feature_id": "requirement.lifecycle", "verification_level": "local_e2e",
                    "passed": soak["passed"], "soak": soak}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(artifact, ensure_ascii=False, indent=2))
    return 0 if artifact["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
