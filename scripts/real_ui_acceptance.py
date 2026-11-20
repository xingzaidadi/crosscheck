"""Execute a YAML/JSON scenario manifest against real applications."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.ui_agent.acceptance import evaluate_real_acceptance  # noqa: E402
from scripts.agent_test import run  # noqa: E402


def execute_manifest(manifest: str | Path, output: str | Path, *, workspace: str = "workspace") -> dict:
    source = Path(manifest).resolve()
    payload = yaml.safe_load(source.read_text(encoding="utf-8")) if source.suffix.lower() != ".json" \
        else json.loads(source.read_text(encoding="utf-8"))
    scenarios = payload.get("scenarios") if isinstance(payload, dict) else payload
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("acceptance manifest requires a non-empty scenarios list")
    output_path = Path(output).resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    samples = []
    for index, scenario in enumerate(scenarios, start=1):
        args = SimpleNamespace(
            url=str(scenario["url"]), instruction=str(scenario["instruction"]),
            workspace=workspace, role=str(scenario.get("role") or "default"), session=scenario.get("session"),
            risk_policy="read_only", allow_write=False, write_scope=None,
            run_id=f"acceptance-{index:03d}", max_steps=int(scenario.get("max_steps") or 30),
            headed=bool(scenario.get("headed")), no_persist=False, no_session_refresh=False,
            interactive_login=bool(scenario.get("interactive_login", True)),
        )
        result = run(args)
        result["scenario_id"] = str(scenario.get("id") or index)
        result["human_intervention"] = result.get("status") == "AUTH_REQUIRED"
        samples.append(result)
    acceptance = evaluate_real_acceptance(samples)
    report = {"manifest": str(source), "samples": samples, "acceptance": acceptance}
    (output_path / "real-ui-acceptance.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="真实业务系统自主 UI 验收")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--workspace", default="workspace")
    args = parser.parse_args()
    report = execute_manifest(args.manifest, args.output, workspace=args.workspace)
    print(json.dumps(report["acceptance"], ensure_ascii=False, indent=2))
    return 0 if report["acceptance"]["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
