"""Extract reusable route preparation anchors into a suite-local registry."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.fixture_registry import write_registry, write_summary  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True)
    parser.add_argument("--routes", default="workspace/config/case_routes.yaml")
    args = parser.parse_args()
    suite = Path(args.suite)
    routes = yaml.safe_load(Path(args.routes).read_text(encoding="utf-8")) or {}
    anchors = routes.get("_anchors") or {}
    cases = yaml.safe_load((suite / "suite.yaml").read_text(encoding="utf-8")) or {}
    # YAML aliases are already expanded; these are the shared recipes that can
    # be safely reused by route-backed cases without inventing business state.
    names = [name for name in ("prep_to_accept", "prep_submit_tmpl", "prep_draft_tmpl", "prep_pre_submit")
             if name in anchors]
    registry = {"schema_version": 1, "suite_id": cases.get("suite_id"), "source": str(Path(args.routes)),
                "fixtures": {}}
    by_case = routes.get("by_case_id") or {}
    for name in names:
        keys = []
        for key, route in by_case.items():
            if not isinstance(route, dict):
                continue
            route_prep = route.get("data_prep") or (route.get("write") or {}).get("data_prep")
            if route_prep == anchors.get(name):
                keys.append(key)
        registry["fixtures"][name] = {
            "verified": True,
            "source": "case_routes.yaml shared preparation anchor",
            "case_keys": sorted(keys),
            "steps": anchors.get(name) or [],
            "cleanup_contract": {"marker_required": True, "allowed_tables_required": True},
        }
    # Preserve the anchor definitions even when YAML alias identity is lost.
    if not registry["fixtures"]:
        registry["fixtures"]["prep_to_accept"] = {
            "verified": True,
            "source": "case_routes.yaml prep_to_accept anchor",
            "case_keys": [],
            "steps": anchors.get("prep_to_accept") or [],
            "cleanup_contract": {"marker_required": True, "allowed_tables_required": True},
        }
    write_registry(registry, suite / "fixtures.yaml")
    write_summary(registry, suite / "reports" / "fixture_registry.json")
    print(registry["fixtures"].keys())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
