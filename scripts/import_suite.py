"""Import Excel/CSV/JSON prose cases into an isolated canonical suite directory."""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.case_source import read_cases
from core.suite_plan import classify_case, suite_fingerprint


def slug(value: str) -> str:
    text = re.sub(r"^\s*[A-Za-z]*\d+\s*[-—_:：]*\s*", "", value or "")
    words = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+", text.lower())
    result = "-".join(words)[:72].strip("-")
    return result or "case"


def canonical_case(raw, suite_id: str, source_name: str) -> dict:
    classified = classify_case(raw)
    case_id = f"{suite_id}/{slug(raw.name)}-{raw.row}"
    return {
        "schema_version": 1,
        "case_id": case_id,
        "title": raw.name,
        "suite_id": suite_id,
        "version": "1.0",
        "source": {"case_key": raw.case_id, "file": source_name, "row": raw.row},
        "priority": raw.level or "P2",
        "status": "draft",
        "scenario_type": classified["intents"][0],
        "business_tags": classified["intents"],
        "layers": {"required": classified["required_layers"]},
        "actors": {},
        "data": {
            "preconditions_text": raw.preconditions,
            "fixtures": [],
        },
        "actions": {
            "source_text": raw.steps_text,
            "ui": [], "api": [], "db": [],
        },
        "assertions": {
            "source_text": raw.expected_text,
            "ui": [], "api": [], "db": [],
        },
        "cleanup": {"strategy": "marker", "targets": []},
        "evidence": {"required": ["screenshot", "api_request", "api_response", "db_result"]},
        "approval": {"status": "draft", "content_hash": ""},
        "execution": {},
        "notes": raw.notes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="把散文 Excel/CSV/JSON 转为隔离的 canonical suite YAML")
    parser.add_argument("source")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--suite-id", default=None)
    parser.add_argument("--suite-name", default=None)
    parser.add_argument("--profile", default="")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    source = Path(args.source).resolve()
    raws = read_cases(source)
    fingerprint = suite_fingerprint(raws)
    sid = args.suite_id or f"{slug(source.stem)}-{fingerprint[:8]}"
    root = Path(args.workspace).resolve() / "suites" / sid
    if root.exists() and any(root.iterdir()) and not args.force:
        raise SystemExit(f"suite 已存在,拒绝覆盖: {root} (需要覆盖时显式加 --force)")
    (root / "cases").mkdir(parents=True, exist_ok=True)
    (root / "specs").mkdir(exist_ok=True)
    (root / "captures").mkdir(exist_ok=True)
    (root / "mappings").mkdir(exist_ok=True)
    (root / "fixtures").mkdir(exist_ok=True)
    (root / "reports").mkdir(exist_ok=True)
    source_dir = root / "source"
    source_dir.mkdir(exist_ok=True)
    shutil.copy2(source, source_dir / source.name)
    suite = {
        "schema_version": 1,
        "suite_id": sid,
        "suite_name": args.suite_name or source.stem,
        "version": "1.0",
        "system": args.profile or "",
        "environment": "unknown",
        "authorization": {"confirmed_non_production": False, "confirmed_by": "", "confirmed_at": ""},
        "profile": args.profile,
        "execution": {"default_layers": ["ui", "api", "db"], "auto_cleanup": True,
                      "stop_on_cleanup_failure": True},
        "source": {"file": f"source/{source.name}", "fingerprint": fingerprint, "case_count": len(raws)},
    }
    (root / "suite.yaml").write_text(yaml.safe_dump(suite, allow_unicode=True, sort_keys=False), encoding="utf-8")
    used: set[str] = set()
    for raw in raws:
        case = canonical_case(raw, sid, source.name)
        filename = f"{raw.case_id}-{slug(raw.name)}.yaml"
        if filename in used:
            filename = f"{raw.case_id}-{raw.row}-{slug(raw.name)}.yaml"
        used.add(filename)
        (root / "cases" / filename).write_text(
            yaml.safe_dump(case, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"suite={sid}\nroot={root}\ncases={len(raws)}\nfingerprint={fingerprint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
