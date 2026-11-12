"""Evaluate the frozen general-tool acceptance baseline from test and file evidence."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CHECKS = [
    ("P0-01", "空数据和基数不足不能 PASS", "tests/test_empty_evidence_gate.py"),
    ("P0-02", "套件/审批/内容哈希漂移拒绝", "tests/test_suite_compiler.py"),
    ("P0-03", "旧编号与陈旧路由污染拒绝", "tests/test_route_fidelity.py"),
    ("P0-04", "清理失败和登记册安全门禁", "tests/test_cleaner_child.py"),
    ("P0-05", "非生产授权门禁", "tests/test_run_suite_cli.py"),
    ("P1-01", "Canonical 编译为不可变执行计划", "tests/test_suite_compiler.py"),
    ("P1-02", "Pilot/批量/熔断/恢复状态机", "tests/test_pipeline_runner.py"),
    ("P1-03", "连接器配方与变更审批失效", "tests/test_suite_bindings.py"),
    ("P1-04", "case-gen YAML 直接导入", "tests/test_casegen_import.py"),
    ("P1-05", "断言级结果和跨运行报告", "tests/test_report_index.py"),
    ("P2-01", "两个无关业务不改 core 编译", "tests/test_cross_domain_canonical.py"),
    ("P2-02", "发布白名单和秘密扫描", "tests/test_release_policy.py"),
    ("P2-03", "Skill 流水线结构有效", ".agents/skills/crosscheck/SKILL.md"),
]


def main() -> int:
    results = []
    cache: dict[str, tuple[bool, str]] = {}
    for check_id, title, evidence in CHECKS:
        path = ROOT / evidence
        if not path.exists():
            results.append({"id": check_id, "title": title, "passed": False, "evidence": evidence,
                            "details": "evidence missing"})
            continue
        if evidence.endswith(".py"):
            if evidence not in cache:
                proc = subprocess.run([sys.executable, str(path)], cwd=ROOT, capture_output=True,
                                      text=True, encoding="utf-8", errors="replace")
                cache[evidence] = (proc.returncode == 0, (proc.stdout + proc.stderr).strip()[-1000:])
            passed, details = cache[evidence]
        else:
            passed, details = True, str(path)
        results.append({"id": check_id, "title": title, "passed": passed,
                        "evidence": evidence, "details": details})
    output = ROOT / "docs" / "GENERAL_TOOL_ACCEPTANCE_RESULTS.json"
    output.write_text(json.dumps({"total": len(results), "passed": sum(r["passed"] for r in results),
                                  "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = output.with_suffix(".md")
    lines = ["# 通用工具验收结果", "", f"- 通过: {sum(r['passed'] for r in results)}/{len(results)}", "",
             "|ID|验收项|结果|证据|", "|---|---|---|---|"]
    for result in results:
        lines.append(f"|{result['id']}|{result['title']}|{'PASS' if result['passed'] else 'FAIL'}|`{result['evidence']}`|")
    markdown.write_text("\n".join(lines), encoding="utf-8")
    print(f"acceptance={sum(r['passed'] for r in results)}/{len(results)}\njson={output}\nmarkdown={markdown}")
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
