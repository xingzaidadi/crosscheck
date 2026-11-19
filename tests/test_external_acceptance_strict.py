import hashlib
import json
from pathlib import Path

import yaml

from scripts.external_acceptance import assess


def test_external_assessment_requires_external_pass_and_hash(tmp_path: Path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    systems = []
    for name, domain, auth, kit in (("a", "inventory", "credential", "antd"),
                                    ("b", "billing", "sso", "element"),
                                    ("c", "hr", "manual", "plain")):
        report = evidence / f"{name}.json"
        report.write_text(json.dumps({"verification_level": "external_pass", "total": 20, "pass": 20,
                                      "failed": 0, "blocked": 0, "inconclusive": 0, "soak_runs": 5}), encoding="utf-8")
        systems.append({"id": name, "business_domain": domain, "base_url": f"https://{name}.test",
                        "auth_mode": auth, "ui_kit": kit, "database": "mysql",
                        "verified_layers": ["ui", "api", "db"], "run_report": f"evidence/{name}.json",
                        "run_report_sha256": hashlib.sha256(report.read_bytes()).hexdigest()})
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(yaml.safe_dump({"policy": {"minimum_systems": 3,
                                                     "minimum_cases_per_system": 20,
                                                     "maximum_inconclusive_rate": 0.1,
                                                     "minimum_soak_runs": 5},
                                             "systems": systems}), encoding="utf-8")
    result = assess(manifest)
    assert result["passed"] is True
    systems[0]["run_report_sha256"] = "bad"
    manifest.write_text(yaml.safe_dump({"systems": systems}), encoding="utf-8")
    assert assess(manifest)["passed"] is False
