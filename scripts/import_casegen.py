"""Import case-gen YAML into an isolated canonical suite without inventing project bindings."""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.suite_plan import classify_case  # noqa: E402


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-").lower() or "case"


def convert_case(item: dict, sid: str, source_name: str, index: int) -> dict:
    expected = item.get("expected") or []
    preconditions = item.get("preconditions") or []
    steps = item.get("steps") or []
    raw = type("Raw", (), {
        "case_id": str(item.get("id") or f"CASE-{index:03d}"),
        "name": str(item.get("title") or item.get("id") or f"Case {index}"),
        "module": str(item.get("level") or ""), "category": str(item.get("level") or ""),
        "tags": str(item.get("type") or ""), "preconditions": "\n".join(map(str, preconditions)),
        "notes": "\n".join(map(str, item.get("notes") or [])),
        "steps_text": "\n".join(str(step) for step in steps),
        "expected_text": "\n".join(str(value) for value in expected),
        "level": str(item.get("priority") or "P2"),
    })()
    classified = classify_case(raw)
    assertions = {"ui": [], "api": [], "db": []}
    for number, value in enumerate(expected, 1):
        observable = str((value or {}).get("observable") or "manual") if isinstance(value, dict) else "manual"
        layer = "ui" if observable == "ui" else "db" if observable in {"db", "ledger_entry", "audit_evidence"} else "api" if observable in {"response", "event"} else None
        if layer:
            assertions[layer].append({"id": f"A-{number:03d}", "source": value})
    required = [layer for layer in ("ui", "api", "db") if assertions[layer]] or classified["required_layers"]
    return {
        "schema_version": 1,
        "case_id": f"{sid}/{_slug(str(item.get('id') or index))}",
        "title": raw.name, "suite_id": sid, "version": "1.0",
        "source": {"case_key": raw.case_id, "file": source_name, "index": index,
                   "traceability": item.get("traceability") or {}},
        "priority": raw.level, "status": "blocked" if item.get("status") == "blocked" else "draft",
        "scenario_type": str(item.get("type") or classified["intents"][0]),
        "business_tags": classified["intents"], "layers": {"required": required},
        "actors": {}, "data": {"preconditions": preconditions, "fixtures": []},
        "actions": {"source_steps": steps, "ui": [], "api": [], "db": []},
        "assertions": {**assertions, "source_expected": expected},
        "cleanup": {"strategy": "marker", "targets": []},
        "evidence": {"required": ["api_response", "db_result"]},
        "approval": {"status": "draft", "content_hash": ""}, "execution": {},
        "open_questions": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="导入 case-gen YAML 为 canonical suite")
    parser.add_argument("source")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--suite-id", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    source = Path(args.source).resolve()
    data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    metadata = data.get("metadata") or {}
    sid = args.suite_id or str(metadata.get("suite_id") or _slug(source.stem))
    root = Path(args.workspace).resolve() / "suites" / sid
    if root.exists() and any(root.iterdir()) and not args.force:
        raise SystemExit(f"suite exists: {root}")
    for name in ("cases", "specs", "captures", "mappings", "fixtures", "reports", "source"):
        (root / name).mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, root / "source" / source.name)
    suite = {"schema_version": 1, "suite_id": sid, "suite_name": metadata.get("title") or sid,
             "version": "1.0", "environment": "unknown", "profile": "",
             "authorization": {"confirmed_non_production": False, "confirmed_by": "", "confirmed_at": ""},
             "source": {"file": f"source/{source.name}", "format": "case-gen"},
             "open_questions": data.get("open_questions") or []}
    (root / "suite.yaml").write_text(yaml.safe_dump(suite, allow_unicode=True, sort_keys=False), encoding="utf-8")
    for index, item in enumerate(data.get("cases") or [], 1):
        case = convert_case(item, sid, source.name, index)
        filename = f"{index:03d}-{_slug(str(item.get('id') or index))}.yaml"
        (root / "cases" / filename).write_text(yaml.safe_dump(case, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"suite={sid} root={root} cases={len(data.get('cases') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
