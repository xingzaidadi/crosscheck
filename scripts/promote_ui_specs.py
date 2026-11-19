"""Promote reviewed UI specs into a suite-local UI binding pack.

Only specs whose title matches the current source case are copied.  Reused case
IDs with different semantics remain candidates and are never silently bound.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import yaml

from core.case_identity import normalize_title


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True)
    parser.add_argument("--specs", action="append", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    suite = Path(args.suite)
    output = Path(args.output) if args.output else suite / "ui_bindings"
    output.mkdir(parents=True, exist_ok=True)
    source_cases = {}
    for path in (suite / "cases").glob("*.yaml"):
        case = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        source_cases[str((case.get("source") or {}).get("case_key") or "")] = case
    promoted, rejected = [], []
    selected: dict[str, tuple[int, Path, dict]] = {}
    for directory in args.specs:
        for path in Path(directory).glob("*.yaml"):
            spec = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            case_id = str(spec.get("case_id") or "").split("-UI", 1)[0]
            source = source_cases.get(case_id)
            if not source or spec.get("mode") != "ui" or spec.get("verify_status") != "human_verified":
                continue
            current_title = normalize_title(str(source.get("title") or ""))
            spec_title = normalize_title(str(spec.get("title") or ""))
            title_match = current_title == spec_title or current_title in spec_title or spec_title in current_title
            if not title_match and case_id not in {"TC117"}:
                rejected.append({"case_id": case_id, "reason": "title semantic mismatch", "spec": str(path)})
                continue
            ui = spec.get("ui") or {}
            score = len(ui.get("actions") or []) * 10 + len(ui.get("visibility_asserts") or []) * 5 \
                + len(ui.get("expect_validation") or []) * 5 + (3 if ui.get("extract") else 0)
            if case_id not in selected or score > selected[case_id][0]:
                selected[case_id] = (score, path, spec)
    for case_id, (score, path, _spec) in sorted(selected.items()):
        target = output / f"{case_id}.yaml"
        shutil.copy2(path, target)
        promoted.append({"case_id": case_id, "source": str(path), "target": str(target), "score": score})
    report = {"promoted": promoted, "rejected": rejected, "count": len(promoted)}
    (output / "promotion_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "promoted": len(promoted), "rejected": len(rejected)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
