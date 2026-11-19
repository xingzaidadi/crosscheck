"""Promote semantically matching reviewed specs into a suite-local binding pack."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.case_identity import normalize_title  # noqa: E402


def case_key(spec: dict, path: Path) -> str:
    raw = str(spec.get("case_id") or path.stem)
    match = re.match(r"^(TC\d+)", raw, re.I)
    return match.group(1).upper() if match else path.stem


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True)
    parser.add_argument("--specs", action="append", required=True)
    parser.add_argument("--output")
    parser.add_argument("--priority")
    args = parser.parse_args()
    suite = Path(args.suite)
    output = Path(args.output) if args.output else suite / "bindings"
    output.mkdir(parents=True, exist_ok=True)
    cases = {}
    for path in (suite / "cases").glob("*.yaml"):
        case = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        key = str((case.get("source") or {}).get("case_key") or "")
        if key:
            cases[key] = case
    promoted, rejected = [], []
    for directory in args.specs:
        for path in sorted(Path(directory).glob("*.yaml")):
            spec = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            key = case_key(spec, path)
            case = cases.get(key)
            if not case or spec.get("verify_status") != "human_verified":
                continue
            if args.priority and case.get("priority") != args.priority:
                continue
            expected = normalize_title(str(case.get("title") or ""))
            actual = normalize_title(str(spec.get("title") or ""))
            title_match = expected == actual or expected in actual or actual in expected
            if not title_match:
                rejected.append({"case_id": key, "reason": "title semantic mismatch", "source": str(path)})
                continue
            target = output / f"{key}.yaml"
            if target.exists():
                existing = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
                if existing.get("mode") == "ui" and spec.get("mode") != "ui":
                    continue
            shutil.copy2(path, target)
            promoted.append({"case_id": key, "mode": spec.get("mode"), "source": str(path), "target": str(target)})
    report = {"promoted": promoted, "rejected": rejected, "count": len(promoted)}
    (output / "promotion_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"promoted": len(promoted), "rejected": len(rejected)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
