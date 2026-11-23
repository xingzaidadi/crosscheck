"""Run the unified business quality gate for local or CI use."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.quality_gate import build_quality_gate, write_quality_gate  # noqa: E402


def _markdown(report: dict) -> str:
    lines = [
        f"# 质量门禁：{report['suite_id']}", "",
        f"- 结果：**{'PASS' if report['passed'] else 'FAIL'}**",
        f"- 成熟度：**{report['maturity']['level']} / {report['maturity']['score']} 分**",
        f"- 前置状态覆盖率：{report['dimensions']['preparation']:.2%}",
        f"- Oracle 覆盖率：{report['dimensions']['oracle']:.2%}",
        f"- INCONCLUSIVE 比例：{report['dimensions']['inconclusive_rate']:.2%}",
        f"- 能力包覆盖率：{report['capability']['coverage']:.2%}（有效：{report['capability']['valid']}）",
        "", "## 资产健康", "",
    ]
    for key, value in report["asset_health"]["counts"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## 阻塞项", ""])
    if report["blockers"]:
        lines.extend(f"- **{item['type']}**：{item['action']}" for item in report["blockers"])
    else:
        lines.append("- 无")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="执行统一业务质量门禁")
    parser.add_argument("--suite", required=True)
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--run-report")
    parser.add_argument("--asset-report")
    parser.add_argument("--output")
    parser.add_argument("--markdown")
    parser.add_argument("--min-score", type=float, default=75.0)
    parser.add_argument("--min-maturity", choices=("M0", "M1", "M2", "M3", "M4"), default="M3")
    parser.add_argument("--min-preparation", type=float, default=1.0)
    parser.add_argument("--min-oracle", type=float, default=1.0)
    parser.add_argument("--max-inconclusive", type=float, default=0.10)
    parser.add_argument("--max-degraded-assets", type=int, default=0)
    parser.add_argument("--max-unhealthy-assets", type=int, default=0)
    parser.add_argument("--min-capability-coverage", type=float, default=1.0)
    parser.add_argument("--allow-missing-capability-pack", action="store_true")
    parser.add_argument("--allow-no-run", action="store_true")
    args = parser.parse_args()
    report = build_quality_gate(
        args.suite, args.workspace, run_report=args.run_report, asset_report=args.asset_report,
        min_score=args.min_score, min_maturity=args.min_maturity,
        min_preparation=args.min_preparation, min_oracle=args.min_oracle,
        max_inconclusive=args.max_inconclusive, max_degraded_assets=args.max_degraded_assets,
        max_unhealthy_assets=args.max_unhealthy_assets, require_run_evidence=not args.allow_no_run,
        min_capability_coverage=args.min_capability_coverage,
        require_capability_pack=not args.allow_missing_capability_pack,
    )
    output = Path(args.output) if args.output else Path(args.suite) / "reports" / "quality_gate.json"
    markdown = Path(args.markdown) if args.markdown else output.with_suffix(".md")
    write_quality_gate(report, output)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({"suite_id": report["suite_id"], "passed": report["passed"],
                      "output": str(output), "markdown": str(markdown),
                      "blockers": len(report["blockers"])}, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
