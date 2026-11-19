"""Audit framework boundaries without importing a business-specific suite."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def audit(root: str | Path = ".", terms_file: str | Path = "tests/fixtures/business_terms.txt") -> dict:
    root = Path(root).resolve()
    terms_path = root / terms_file
    terms = [line.strip() for line in terms_path.read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.lstrip().startswith("#")] if terms_path.exists() else []
    hits = []
    core = root / "core"
    for path in sorted(core.rglob("*.py")):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for term in terms:
                if term.lower() in line.lower():
                    hits.append({"file": path.relative_to(root).as_posix(), "line": line_no,
                                 "term": term, "text": line.strip()[:200]})
    suite_refs = []
    for path in sorted((root / "core").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "workspace/suites" in text or "workspace\\suites" in text:
            suite_refs.append(path.relative_to(root).as_posix())
    return {"schema_version": 1, "passed": not hits and not suite_refs,
            "business_word_hits": hits, "suite_path_references": suite_refs,
            "checked": ["core business terms", "core suite path coupling"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="framework_boundary_audit.json")
    args = parser.parse_args()
    result = audit(args.root)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
