"""Generate a vendor-test-agent suite skeleton from a safe project config."""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

import yaml

from check_case_readiness import check


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-").lower() or "project"


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def generate(config_path: Path, workspace: Path, force: bool = False) -> Path:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    readiness = check(config_path)
    if readiness["errors"]:
        raise ValueError("configuration is blocked: " + "; ".join(readiness["errors"][:5]))
    project = data["project"]
    suite_id = f"{_slug(project['system_id'])}-fullstack-v1"
    root = workspace / "suites" / suite_id
    if root.exists() and any(root.iterdir()) and not force:
        raise FileExistsError(f"suite exists: {root}; use --force to replace")
    if root.exists():
        shutil.rmtree(root)
    for name in ("cases", "fixtures", "captures", "mappings", "reports", "source"):
        (root / name).mkdir(parents=True, exist_ok=True)
    suite = {
        "schema_version": 1,
        "suite_id": suite_id,
        "suite_name": f"{project['system_id']} 全栈测试套件",
        "version": "1.0",
        "system": project["system_id"],
        "environment": project["environment"],
        "authorization": {
            "confirmed_non_production": bool(project["non_production_confirmed"]),
            "confirmed_by": project["confirmed_by"],
            "confirmed_at": project["confirmed_at"],
        },
        "base_url": project["base_url"],
        "profile": project["profile"],
        "database": {"readonly": data["database"]["readonly_profile"], "write": None},
        "execution": {"default_layers": ["api", "db"], "auto_cleanup": True,
                       "stop_on_cleanup_failure": True},
        "source": {"file": f"source/{config_path.name}", "format": "fullstack-onboarding"},
        "open_questions": [],
    }
    _write(root / "suite.yaml", suite)
    shutil.copy2(config_path, root / "source" / config_path.name)

    api = data["api"]["order_create"]
    tables = data["database"]["tables"]
    cleanup = [{"table": table, "column": data["database"]["cleanup"]["marker_field"]}
               for table in data["database"]["cleanup"]["allowed_tables"]]
    case = {
        "schema_version": 1,
        "case_id": f"{suite_id}/api-order-idempotency-001",
        "title": "创建订单：相同幂等键不产生重复订单",
        "suite_id": suite_id,
        "version": "1.0",
        "source": {"case_key": "API-ORDER-001", "file": config_path.name, "row": 1},
        "priority": "P0", "status": "draft", "scenario_type": "idempotency",
        "business_tags": ["api", "order", "idempotency", "data-integrity"],
        "layers": {"required": ["api", "db"]},
        "actors": {"operator": {"profile": project["profile"], "act_as": "ordinary_user"}},
        "data": {"fixtures": [{"name": "order_request", "recipe": api["request_fixture"], "parameters": {}}]},
        "actions": {"ui": [], "api": [{"request": {"method": api["method"], "url": api["path"]}}], "db": []},
        "assertions": {
            "ui": [],
            "api": [{"id": "A-API-001", "response": {"path": "status", "equals": api["success_status"]}},
                    {"id": "A-API-002", "response": {"path": "body.orderId", "exists": True}}],
            "db": [{"id": "A-DB-001", "row_count": {"table": tables["order"], "where": "test_marker = :marker", "equals": 1}},
                   {"id": "A-DB-002", "row_count": {"table": tables["idempotency"], "where": "idempotency_key = :key", "equals": 1}}],
        },
        "cleanup": {"strategy": "marker", "targets": cleanup},
        "evidence": {"required": ["api_request", "api_response", "db_result"]},
        "approval": {"status": "draft", "content_hash": ""},
        "execution": {
            "mode": "api", "kind": "write", "act_via": "api", "feature": "order",
            "db": data["database"]["readonly_profile"], "base_url": project["base_url"],
            "session": data["actors"]["ordinary_user"]["session_file"],
            "request": {"method": api["method"], "url": api["path"]},
            "engine_assertions": {
                "response": {"status": api["success_status"]},
                "db": [{"table": tables["order"], "where": "test_marker = :marker", "row_count": 1},
                       {"table": tables["idempotency"], "where": "idempotency_key = :key", "row_count": 1}],
            },
            "assertion_bindings": {
                "A-API-001": {"layer": "api", "proof": "api_response", "ref": "engine_assertions.response"},
                "A-API-002": {"layer": "api", "proof": "api_response", "ref": "engine_assertions.response"},
                "A-DB-001": {"layer": "db", "proof": "db_assertion", "ref": "engine_assertions.db[0]"},
                "A-DB-002": {"layer": "db", "proof": "db_assertion", "ref": "engine_assertions.db[1]"},
            },
            "allowed_tables": data["database"]["cleanup"]["allowed_tables"],
        },
        "open_questions": ["补充真实请求体和幂等键注入方式", "确认重复请求的第二次响应断言"],
    }
    _write(root / "cases" / "001-api-order-idempotency.yaml", case)
    return root


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate full-stack suite skeleton")
    parser.add_argument("config", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        root = generate(args.config, args.workspace, args.force)
    except Exception as exc:
        print(f"BLOCKED: {exc}")
        return 1
    print(f"suite={root.name}")
    print(f"root={root}")
    print("status=draft")
    print("next=run score_suite.py, then fill execution details before approval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
