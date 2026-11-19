"""Render UI-only JSON using the canonical evidence-aware report."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.interfaces import CaseResult, Verdict
from core.run_report import render


def _layer_outcome(verdict: str | None) -> tuple[bool | None, str | None]:
    """Keep INCONCLUSIVE distinct from a failed assertion in the HTML report."""
    if verdict == "PASS":
        return True, verdict
    if verdict == "FAIL":
        return False, verdict
    if verdict == "INCONCLUSIVE":
        return None, verdict
    return None, verdict


def render_summary(run_dir: str | Path) -> Path:
    run_dir = Path(run_dir).resolve()
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    mapping = {"PASS": Verdict.PASS, "FAIL": Verdict.FAIL, "INCONCLUSIVE": Verdict.PARTIAL,
               "BLOCKED": Verdict.BLOCKED, "ENV_ERROR": Verdict.ENV_ERROR, "DEFERRED": Verdict.SKIP}
    results = []
    for item in summary.get("cases", []):
        execution = item.get("execution") or {}
        acceptance = item.get("acceptance") or {}
        tech = execution.get("technical_verdict")
        acceptance_verdict = acceptance.get("verdict")
        technical_ok, technical_status = _layer_outcome(tech)
        acceptance_ok, acceptance_status = _layer_outcome(acceptance_verdict)
        action_rows = execution.get("actions_replayed") or []
        assertions = acceptance.get("results") or []
        unresolved = acceptance.get("unresolved") or []
        assertion_rows = [
            {"id": row.get("id") or row.get("assertion_id") or f"assertion-{index}",
             "expected": row.get("source") or row.get("value") or row.get("expected"),
             "actual": row.get("actual"), "ok": row.get("passed")}
            for index, row in enumerate(assertions, start=1)
        ]
        assertion_rows.extend({"id": f"unresolved-{index}", "expected": text,
                               "actual": "未执行：缺少可执行 UI 断言", "ok": None}
                              for index, text in enumerate(unresolved, start=1))
        evidence = dict(item.get("evidence") or {})
        diagnostics = evidence.pop("network_diagnostics", None)
        evidence.pop("api", None)
        evidence.pop("db", None)
        source = {
            "module": item.get("source_module"),
            "preconditions": item.get("source_preconditions"),
            "steps": item.get("source_steps"),
            "expected": item.get("source_expected"),
        }
        did = []
        for index, row in enumerate(action_rows, start=1):
            status = "PASS" if row.get("ok") is True else (
                "未执行" if row.get("ok") is None else "FAIL"
            )
            target = row.get("target") or row.get("text") or "（未解析控件）"
            detail = row.get("error") or row.get("actual") or ""
            did.append(f"步骤 {index}: {row.get('action') or '操作'} {target} — {status}"
                       + (f"；{detail}" if detail else ""))
        for index, row in enumerate(assertion_rows, start=1):
            row["id"] = row.get("id") or f"assertion-{index}"
        results.append(CaseResult(
            case_id=str(item.get("case_id") or ""), title=str(item.get("title") or ""),
            verdict=mapping.get(str(item.get("verdict") or ""), Verdict.SKIP),
            details=[str(item.get("reason") or "")], kind="ui-only", mode="ui",
            duration_s=float(execution.get("duration_s") or 0), phase_verdict=f"UI_{item.get('verdict')}",
            report={
                "source": source,
                "did": did,
                "layers": [
                    *([{"name": "执行说明", "ok": None,
                       "actual": str(item.get("reason") or item.get("note") or "未执行") }]
                      if item.get("reason") or item.get("note") else []),
                    {"name": "UI 技术执行", "ok": technical_ok, "status": technical_status,
                     "expected": "页面打开且动作回放成功", "actual": tech or "NOT_RUN"},
                    {"name": "UI 业务验收", "ok": acceptance_ok, "status": acceptance_status,
                     "expected": "必需 UI 断言覆盖率 100% 且全部通过",
                     "actual": f"{acceptance_verdict or 'NOT_RUN'} / coverage={acceptance.get('coverage', 0)}",
                     "cols": ["断言", "预期", "实际", "结果"],
                     "rows": [[row.get("id"), row.get("expected"), row.get("actual"),
                               "PASS" if row.get("ok") is True else "FAIL" if row.get("ok") is False
                               else "NOT_EXECUTED"] for row in assertion_rows]},
                    {"name": "API（未执行）", "ok": None, "actual": "NOT_EXECUTED：UI-first 阶段不执行 API 验收"},
                    {"name": "DB（未执行）", "ok": None, "actual": "NOT_EXECUTED：UI-first 阶段不执行数据库验收"},
                ],
                "evidence": evidence,
                "ui_diagnostics": diagnostics,
                "technical_execution": execution,
                "business_acceptance": acceptance,
            },
        ))
    return render(str(summary.get("run_id") or run_dir.name), results, run_dir,
                  write_summary=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    args = parser.parse_args()
    render_summary(args.run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
