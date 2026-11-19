"""Audit a JSON/YAML case list and emit a quality report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from core.case_auditor import audit_cases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = yaml.safe_load(args.source.read_text(encoding="utf-8")) or {}
    cases = data.get("cases", data) if isinstance(data, dict) else data
    report = audit_cases(cases if isinstance(cases, list) else [cases])
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["ready"] == report["total"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
