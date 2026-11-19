"""Run the unified local delivery acceptance and emit an artifact."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.local_delivery_acceptance import run_local_delivery_acceptance


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_local_delivery_acceptance(repetitions=args.repetitions, output=args.output)
    print(json.dumps({"passed": result["passed"], "artifact": str(args.output),
                      "artifact_hash": result["artifact_hash"], "gates": result["gates"]}, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
