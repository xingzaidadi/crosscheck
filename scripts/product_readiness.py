"""Generate the unified product readiness report for a canonical suite."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.product_readiness import assess_product_readiness, write_product_readiness  # noqa: E402
from core.suite_dsl import load_suite  # noqa: E402


def _load_json(path: str | None) -> dict | None:
    if not path:
        return None
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return value if isinstance(value, dict) else None


def _markdown(report: dict) -> str:
    maturity = report["maturity"]
    complexity = report["complexity"]
    lines = [
        f"# 产品就绪度评估：{report['suite_id']}", "",
        f"- 业务复杂度：**{complexity['level']}**",
        f"- 自动化成熟度：**{maturity['level']} / {maturity['score']} 分**",
        f"- 生产就绪：**{report['production_readiness']}**",
        f"- 用例数量：{report['total_cases']}", "",
        "## 分项指标", "", "| 指标 | 数值 |", "|---|---:|",
    ]
    for key, value in maturity["dimensions"].items():
        lines.append(f"| {key} | {value:.2%} |" if isinstance(value, float) and key != "run_stability" else f"| {key} | {value} |")
    lines.extend(["", "## 复杂度分布", "", "| 等级 | 用例数 |", "|---|---:|"])
    for level, count in complexity["distribution"].items():
        lines.append(f"| {level} | {count} |")
    oracle = report["oracle_readiness"]
    preparation = report["preparation"]
    lines.extend(["", "## 前置状态与业务 Oracle", "",
                  f"- 前置状态准备覆盖率：{preparation['coverage']:.2%}",
                  f"- Oracle 完整覆盖率：{oracle['coverage']:.2%}",
                  f"- Oracle 已就绪：{oracle['ready']}，部分完成：{oracle['partial']}，阻塞：{oracle['blocked']}"])
    lines.extend(["", "## 阻塞项", ""])
    if report["blockers"]:
        for item in report["blockers"]:
            lines.append(f"- **{item['type']}**：{item['action']}")
    else:
        lines.append("- 无")
    lines.extend(["", "## 下一步动作", ""])
    for action in report["next_actions"] or ["保持现有回归并持续收集稳定性数据"]:
        lines.append(f"1. {action}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="生成业务复杂度、自动化成熟度和生产就绪度报告")
    parser.add_argument("--suite", required=True)
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--run-report")
    parser.add_argument("--output")
    parser.add_argument("--markdown")
    args = parser.parse_args()
    suite, cases = load_suite(args.suite)
    report = assess_product_readiness(suite, cases, run_report=_load_json(args.run_report),
                                      suite_dir=args.suite, workspace=args.workspace)
    output = Path(args.output) if args.output else Path(args.suite) / "reports" / "product_readiness.json"
    write_product_readiness(report, output)
    markdown = Path(args.markdown) if args.markdown else output.with_suffix(".md")
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({"json": str(output), "markdown": str(markdown),
                      "complexity": report["complexity"]["level"],
                      "maturity": report["maturity"],
                      "production_readiness": report["production_readiness"]}, ensure_ascii=False, indent=2))
    return 0 if report["production_readiness"] == "READY" else 4


if __name__ == "__main__":
    raise SystemExit(main())
