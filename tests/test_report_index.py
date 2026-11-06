"""
报告跨运行聚合 验证(离线):
  1) render 每次运行除 report.html 外,落一份机器可读 summary.json。
  2) render_index 扫 runs 目录各 summary.json → 一页总览 index.html(历次通过率 + 直达各报告)。

跑:python tests/test_report_index.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.run_report import render, render_index  # noqa: E402
from core.interfaces import CaseResult, Verdict  # noqa: E402


def main():
    print("报告跨运行聚合 验证:\n")
    root = Path(tempfile.mkdtemp()) / "runs"

    # 1) render 落 summary.json
    rd = root / "run_A"
    rd.mkdir(parents=True)
    results = [
        CaseResult(case_id="T1", verdict=Verdict.PASS, title="用例1", kind="write", mode="api"),
        CaseResult(case_id="T2", verdict=Verdict.FAIL, title="用例2", kind="query", mode="reconcile"),
        CaseResult(case_id="T3", verdict=Verdict.SKIP, title="用例3"),
    ]
    render("run_A", results, rd)
    sj = json.loads((rd / "summary.json").read_text(encoding="utf-8"))
    assert (rd / "report.html").exists()
    assert sj["total"] == 3 and sj["pass"] == 1 and sj["fail"] == 1 and sj["skip"] == 1, sj
    assert len(sj["cases"]) == 3
    print("    ✓ render 落 summary.json:total=3 pass=1 fail=1 skip=1,逐例明细齐")

    # 2) 再造一次运行,render_index 聚合两次
    rd2 = root / "run_B"
    rd2.mkdir(parents=True)
    render("run_B", [CaseResult(case_id="T1", verdict=Verdict.PASS, title="用例1")], rd2)

    idx = render_index(root)
    html = idx.read_text(encoding="utf-8")
    assert "run_A" in html and "run_B" in html, "总览应列出两次运行"
    assert "通过率" in html and "趋势" in html
    assert "run_A/report.html" in html and "run_B/report.html" in html, "应能直达各报告"
    print("    ✓ render_index 总览:列出 run_A/run_B、通过率、趋势、直达各报告链接")
    print("\n全部通过 ✅  —— 报告跨运行聚合(summary.json + 总览 index.html)就位")


if __name__ == "__main__":
    main()
