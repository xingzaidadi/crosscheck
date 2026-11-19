from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

from scripts.framework_score import score_onboarding


ROOT = Path(__file__).resolve().parent.parent


def _write_dataset(root: Path, name: str, table: str, endpoint: str) -> tuple[Path, Path]:
    cases = root / f"{name}.csv"
    cases.write_text("case_id,name,preconditions,steps,expected,level\n"
                     f"C1,{name} query,existing data,call {endpoint},row in {table},P1\n", encoding="utf-8")
    profile = root / f"{name}.yaml"
    profile.write_text(yaml.safe_dump({
        "suite_id": name,
        "base_url": "https://example.invalid",
        "db": {"readonly": f"{name}-db"},
        "bindings": {"api": [endpoint], "db": [table]},
        "oracles": {"api": "response", "db": "row"},
        "fixture_recipes": {"existing data": "database_seed"},
    }), encoding="utf-8")
    return cases, profile


def _run(root: Path, name: str, table: str, endpoint: str) -> Path:
    cases, profile = _write_dataset(root, name, table, endpoint)
    workspace = root / f"ws-{name}"
    result = subprocess.run([sys.executable, str(ROOT / "run_onboard.py"), "onboard", "--cases", str(cases),
                             "--profile", str(profile), "--workspace", str(workspace)],
                            cwd=ROOT, capture_output=True, text=True, check=True)
    payload = json.loads(result.stdout)
    return Path(payload["output"])


def test_two_systems_share_output_schema_and_dual_score(tmp_path: Path):
    first = _run(tmp_path, "alpha", "record_a", "/api/a")
    second = _run(tmp_path, "beta", "record_b", "/api/b")
    names_a = sorted(path.relative_to(first).as_posix() for path in first.rglob("*") if path.is_file())
    names_b = sorted(path.relative_to(second).as_posix() for path in second.rglob("*") if path.is_file())
    assert names_a == names_b
    assert score_onboarding(first)["framework_score"] == score_onboarding(second)["framework_score"]


def test_same_input_has_same_onboarding_id(tmp_path: Path):
    cases, profile = _write_dataset(tmp_path, "stable", "records", "/api/records")
    command = [sys.executable, str(ROOT / "run_onboard.py"), "onboard", "--cases", str(cases),
               "--profile", str(profile), "--workspace", str(tmp_path / "workspace")]
    first = json.loads(subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True).stdout)
    second = json.loads(subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True).stdout)
    assert first["onboarding_id"] == second["onboarding_id"]
