"""Check project integration placeholders and unsafe environment values before execution."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml


PLACEHOLDER = re.compile(r"replace-with|TODO|TBD|example\.com", re.IGNORECASE)
PRODUCTION = re.compile(r"(^|[.\-/])(prod|production)([.\-/]|$)", re.IGNORECASE)
SECRET = re.compile(r"password|secret|token|api[_-]?key", re.IGNORECASE)


def _walk(value, path=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, f"{path}[{index}]")
    else:
        yield path, value


def check(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    errors, warnings = [], []
    inspect_data = dict(data)
    for optional_section in ("mq", "scheduled_jobs"):
        section = inspect_data.get(optional_section)
        if isinstance(section, dict) and section.get("enabled") is False:
            inspect_data.pop(optional_section, None)
    for field, value in _walk(inspect_data):
        text = str(value)
        if PLACEHOLDER.search(text):
            errors.append(f"placeholder: {field}={text}")
        if PRODUCTION.search(text) and not ("non-production" in text.lower() or "non_production" in text.lower()):
            errors.append(f"production-like value: {field}={text}")
        if SECRET.search(field) and value not in (None, "", False):
            warnings.append(f"credential-like field should not contain a value: {field}")
    authorization = data.get("authorization") or data.get("project") or {}
    if authorization.get("confirmed_non_production") is False or authorization.get("non_production_confirmed") is False:
        errors.append("non-production authorization is not confirmed")
    return {"file": str(path), "ok": not errors, "errors": errors, "warnings": warnings}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args(argv)
    failed = False
    for path in args.paths:
        result = check(path)
        print(f"{path}: {'READY-CANDIDATE' if result['ok'] else 'BLOCKED'}")
        for item in result["errors"] + result["warnings"]:
            print(f"  - {item}")
        failed = failed or not result["ok"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
