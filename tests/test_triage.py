"""
失败自动归因 验证(离线、零业务):失败用例分 环境/建模错/真bug候选。

跑:python tests/test_triage.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.triage import classify, summarize  # noqa: E402
from core.interfaces import CaseResult, Verdict  # noqa: E402


def main():
    print("失败自动归因 验证:\n")
    assert classify(Verdict.PASS, [])["bucket"] == "pass"
    assert classify(Verdict.ENV_ERROR, ["执行异常: 连接超时"])["bucket"] == "environment"
    assert classify(Verdict.FAIL, ["未建模:缺 request(写动作)"])["bucket"] == "modeling"
    assert classify(Verdict.FAIL, ["[demand_request] 查询失败: no such column x"])["bucket"] == "modeling"
    assert classify(Verdict.FAIL, ["字段不一致: amount 提交'50' vs 落库'999'"])["bucket"] == "bug_candidate"
    assert classify(Verdict.FAIL, ["预期被拒,但响应成功(code=200)"])["bucket"] == "bug_candidate"
    assert classify(Verdict.FAIL, ["计算不变量不符: amount"])["bucket"] == "bug_candidate"
    print("    ✓ 分桶:PASS/环境/建模错(缺request·SQL错)/真bug候选(字段不符·该拒没拒·计算不符)")

    results = [
        CaseResult(case_id="A", verdict=Verdict.PASS),
        CaseResult(case_id="B", verdict=Verdict.FAIL, details=["字段不一致: x"]),
        CaseResult(case_id="C", verdict=Verdict.FAIL, details=["预期被拒,但响应成功"]),
        CaseResult(case_id="D", verdict=Verdict.ENV_ERROR, details=["登录失效"]),
        CaseResult(case_id="E", verdict=Verdict.SKIP, details=["未人审"]),
    ]
    s = summarize(results)
    assert s["buckets"].get("bug_candidate") == 2 and set(s["bug_candidates"]) == {"B", "C"}, s
    assert s["buckets"].get("environment") == 1 and s["buckets"].get("pass") == 1
    print(f"    ✓ 批量汇总:{s['buckets']};疑似缺陷 {s['bug_candidates']}")
    print("\n全部通过 ✅  —— 失败自动归因就位(真bug候选一眼挑出,少让人判)")


if __name__ == "__main__":
    main()
