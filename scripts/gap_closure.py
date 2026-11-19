"""Generate safe binding candidates and readiness diagnostics for a suite."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.binding_candidates import generate_binding_candidate
from core.suite_dsl import load_suite


def _load_observations(workspace: Path, site: str) -> list[dict]:
    observations = []
    for path in (
        workspace / "knowledge_base" / "api_catalog" / f"{site}.json",
        workspace / "knowledge_base" / "contracts" / f"{site}.json",
    ):
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else list(data.get("endpoints") or [])
        observations.extend(item for item in rows if isinstance(item, dict))
    return observations


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate review-only bindings for suite gaps")
    parser.add_argument("--suite", required=True)
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--output")
    args = parser.parse_args()
    suite_path = Path(args.suite)
    workspace = Path(args.workspace)
    suite, cases = load_suite(suite_path)
    fingerprint = str((suite.get("source") or {}).get("fingerprint") or "")
    observations = _load_observations(workspace, str(suite.get("profile") or suite.get("system") or ""))
    candidates = [generate_binding_candidate(case, observations, suite_fingerprint=fingerprint) for case in cases]
    report = {
        "suite_id": suite.get("suite_id"),
        "suite_fingerprint": fingerprint,
        "total": len(candidates),
        "matched": sum(bool(item.get("execution")) for item in candidates),
        "review_required": len(candidates),
        "candidates": candidates,
    }
    output = Path(args.output) if args.output else suite_path / "reports" / "binding_candidates.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
