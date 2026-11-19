"""Evaluate the frozen general-tool acceptance baseline."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CHECKS = [
    ("P0-01", "Empty evidence cannot pass", "tests/test_empty_evidence_gate.py"),
    ("P0-02", "Approval and content hash drift rejection", "tests/test_suite_compiler.py"),
    ("P0-03", "Stale route fidelity rejection", "tests/test_route_fidelity.py"),
    ("P0-04", "Cleanup and registry safety gate", "tests/test_cleaner_child.py"),
    ("P0-05", "Non-production authorization gate", "tests/test_run_suite_cli.py"),
    ("P1-01", "Canonical immutable execution plan", "tests/test_suite_compiler.py"),
    ("P1-02", "Pilot batch resume state machine", "tests/test_pipeline_runner.py"),
    ("P1-03", "Connector binding approval", "tests/test_suite_bindings.py"),
    ("P1-04", "Case-gen YAML import", "tests/test_casegen_import.py"),
    ("P1-05", "Assertion and run report index", "tests/test_report_index.py"),
    ("P2-01", "Cross-domain canonical compilation", "tests/test_cross_domain_canonical.py"),
    ("P2-02", "Release allowlist and secret scan", "tests/test_release_policy.py"),
    ("P2-03", "Skill pipeline structure", ".agents/skills/crosscheck/SKILL.md"),
    ("P2-04", "Installed product CLI and templates", "tests/test_product_cli.py"),
    ("P2-05", "Knowledge and system-map extensions", "tests/test_product_extensions.py"),
    ("P2-06", "Two isolated system plans", "tests/test_two_system_e2e.py"),
    ("P2-07", "Public Playwright adapter", "tests/test_playwright_adapter.py"),
    ("P2-08", "Local UI API DB cleanup demo", "tests/test_local_demo.py"),
    ("P2-09", "External two-system evidence contract", "tests/test_external_acceptance.py"),
    ("P2-10", "Package resource completeness", "tests/test_package_resources.py"),
    ("P2-11", "API session refresh and redaction", "tests/test_api_refresh_evidence.py"),
    ("P2-12", "Protocol and database plugin contracts", "tests/test_plugins.py"),
    ("P2-13", "Database dialect guard", "tests/test_db_dialect_guard.py"),
    ("P2-14", "Security check entrypoint", "tests/test_security_check.py"),
    ("P2-15", "Pytest entry and SQLite fixtures", "tests/test_report_index.py"),
    ("P2-16", "Binding lifecycle drift and external adapters", "tests/test_gap_closures.py"),
    ("P2-17", "UI-first readiness and file evidence", "tests/test_ui_first.py"),
    ("P2-18", "Evidence sufficiency by test objective", "tests/test_evidence_sufficiency.py"),
]


def main() -> int:
    results = []
    cache: dict[str, tuple[bool, str]] = {}
    for check_id, title, evidence in CHECKS:
        path = ROOT / evidence
        if not path.exists():
            results.append({"id": check_id, "title": title, "passed": False,
                            "evidence": evidence, "details": "evidence missing"})
            continue
        if evidence.endswith(".py"):
            if evidence not in cache:
                env = os.environ.copy()
                existing_pythonpath = env.get("PYTHONPATH", "")
                env["PYTHONPATH"] = str(ROOT) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
                process = subprocess.run([sys.executable, str(path)], cwd=ROOT, env=env,
                                         capture_output=True, text=True, encoding="utf-8", errors="replace")
                cache[evidence] = (process.returncode == 0, (process.stdout + process.stderr).strip()[-1000:])
            passed, details = cache[evidence]
        else:
            passed, details = True, str(path)
        level, environment = "contract", "offline"
        if evidence in {"tests/test_local_demo.py", "tests/test_two_system_e2e.py"}:
            level, environment = "local_e2e", "local_mock"
        elif evidence == "tests/test_external_acceptance.py":
            level, environment = "external_ready", "external_manifest"
        results.append({"id": check_id, "title": title, "passed": passed,
                        "verification_level": level, "environment": environment,
                        "evidence": evidence, "details": details})
    payload = {"total": len(results), "passed": sum(item["passed"] for item in results), "results": results}
    output = ROOT / "docs" / "GENERAL_TOOL_ACCEPTANCE_RESULTS.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = output.with_suffix(".md")
    lines = ["# General Tool Acceptance", "", f"- Passed: {payload['passed']}/{payload['total']}", "",
             "|ID|Check|Result|Level|Evidence|", "|---|---|---|---|---|"]
    for result in results:
        lines.append(f"|{result['id']}|{result['title']}|{'PASS' if result['passed'] else 'FAIL'}|"
                     f"{result['verification_level']}|`{result['evidence']}`|")
    markdown.write_text("\n".join(lines), encoding="utf-8")
    print(f"acceptance={payload['passed']}/{payload['total']}\njson={output}\nmarkdown={markdown}")
    return 0 if payload["passed"] == payload["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
