"""Create a safe full-stack onboarding report without contacting the target system."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from check_case_readiness import check


def _required_fields(data: dict) -> list[tuple[str, object]]:
    project = data.get("project") or {}
    api = data.get("api") or {}
    order = api.get("order_create") or {}
    database = data.get("database") or {}
    return [
        ("project.system_id", project.get("system_id")),
        ("project.profile", project.get("profile")),
        ("project.base_url", project.get("base_url")),
        ("project.non_production_confirmed", project.get("non_production_confirmed")),
        ("actors.ordinary_user.session_file", (data.get("actors") or {}).get("ordinary_user", {}).get("session_file")),
        ("database.readonly_profile", database.get("readonly_profile")),
        ("api.order_create.path", order.get("path")),
        ("api.order_create.request_fixture", order.get("request_fixture")),
    ]


def build_report(config_path: Path) -> dict:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    readiness = check(config_path)
    missing = [name for name, value in _required_fields(data) if value in (None, "", False)]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": str(config_path),
        "status": "blocked" if readiness["errors"] or missing else "ready-candidate",
        "network_contacted": False,
        "missing_required_fields": missing,
        "errors": readiness["errors"],
        "warnings": readiness["warnings"],
        "next_steps": [
            "Fill all replace-with-* values and confirm non-production authorization.",
            "Run vendor-test-agent preflight for db, api, and site capabilities.",
            "Run score_suite.py and then run_suite.py --plan-only.",
            "Only after human review, change case status from draft to ready.",
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Safe full-stack project onboarding")
    parser.add_argument("config", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    report = build_report(args.config)
    output = args.out or args.config.with_name("onboarding-report.json")
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"status={report['status']}")
    print(f"network_contacted={report['network_contacted']}")
    print(f"missing={len(report['missing_required_fields'])}")
    print(f"report={output}")
    return 0 if report["status"] == "ready-candidate" else 1


if __name__ == "__main__":
    raise SystemExit(main())
