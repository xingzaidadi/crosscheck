"""计分卡 验证(离线、零业务):验"事实→分数"的确定性折算与加权汇总。
跑:python tests/test_scorecard.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.scorecard import (  # noqa: E402
    score_runnability, score_coverage, score_autobuild, score_oracle,
    score_demo, aggregate, build_scorecard,
)


def main():
    print("计分卡 验证:\n")

    # 可运行性:全绿=10,半绿≈5,0 条=0
    assert score_runnability(100, 100).score == 10.0
    assert score_runnability(100, 50).score == 5.0
    assert score_runnability(0, 0).score == 0.0
    print("    ✓ 可运行性按通过率线性折算,空仓=0(不给假满分)")

    # 覆盖率:80% 满分,55% 旧门禁约 6.9,0% = 0
    assert score_coverage(80).score == 10.0
    assert abs(score_coverage(55).score - 6.9) < 0.05
    assert score_coverage(0).score == 0.0
    assert score_coverage(95).score == 10.0  # 超锚点封顶
    print("    ✓ 覆盖率以 80% 为满分锚点,低覆盖率压分,超锚点封顶")

    # 自动建模(最大瓶颈):85% 综合=满分;全 false=0
    full = score_autobuild(142, 142, 142)
    assert full.score == 10.0, full.score
    assert score_autobuild(142, 0, 0).score == 0.0
    # ready 85% + 零路由 0 → blended=0.595 → /0.85*10≈7.0
    partial = score_autobuild(100, 85, 0)
    assert 6.5 <= partial.score <= 7.5, partial.score
    print("    ✓ 自动建模覆盖:ready+零人工路由 加权,85% 综合为满分锚点")

    # oracle:80% 覆盖=9,叠加差异模式+1=10
    assert abs(score_oracle(80, 100, diff_mode=False).score - 9.0) < 0.05
    assert abs(score_oracle(80, 100, diff_mode=True).score - 10.0) < 0.05
    assert score_oracle(0, 100).score == 0.0
    # partial 半权:40 ready + 80 partial = 40+40=80 有效 → 等同 80 ready 的 9.0
    assert abs(score_oracle(40, 100, cases_partial=80).score - 9.0) < 0.05
    # 纯 partial 诚实半权(不是降标准):6 partial/142 = 3 有效 → 低分但非 0
    assert 0.0 < score_oracle(0, 142, cases_partial=6).score < 0.5
    print("    ✓ oracle 覆盖 80%=9,差异测试模式再+1 封顶 10,partial 半权诚实计入")

    # demo:布尔
    assert score_demo(True).score == 10.0
    assert score_demo(False).score == 0.0
    print("    ✓ demo 三源打通为布尔项(10/0)")

    # 加权汇总:全满分→综合 10
    perfect = build_scorecard(
        tests_total=200, tests_passed=200, coverage_pct=85,
        cases_total=142, ready_true=142, zero_route=142,
        cases_with_oracle=142, diff_mode=True, three_source_ok=True,
    )
    assert perfect["overall"] == 10.0, perfect["overall"]
    assert len(perfect["dimensions"]) == 5
    print("    ✓ 全维满分 → 综合 10.0")

    # 复现当前基线(7.5 档附近):半自动、覆盖中等
    baseline = build_scorecard(
        tests_total=199, tests_passed=185, coverage_pct=55,
        cases_total=142, ready_true=50, zero_route=0,
        cases_with_oracle=40, diff_mode=False, three_source_ok=True,
    )
    assert 4.5 <= baseline["overall"] <= 7.5, baseline["overall"]
    print(f"    ✓ 当前基线复算 overall={baseline['overall']}(自动建模拖分,符合 7.5 档诊断)")

    # 权重归一化:给非常规权重也能正确汇总
    from core.scorecard import DimensionScore
    agg = aggregate([DimensionScore("a", 10.0, 1.0, ""), DimensionScore("b", 0.0, 1.0, "")])
    assert agg["overall"] == 5.0
    print("    ✓ 权重归一化正确")

    # 两维分母解耦:autobuild 分母用自己的语料(63),oracle 分母用套件(142),不混用。
    # 回归历史缺陷——旧口径 max(63,142) 会把 autobuild 分母顶成 142,分子却来自 63 语料。
    decoupled = build_scorecard(
        tests_total=200, tests_passed=200, coverage_pct=85,
        cases_total=63, ready_true=40, zero_route=15,
        cases_with_oracle=4, cases_partial=46, diff_mode=False, three_source_ok=True,
        oracle_total=142,
    )
    ab = next(d for d in decoupled["dimensions"] if d["name"] == "autobuild")
    orc = next(d for d in decoupled["dimensions"] if d["name"] == "oracle")
    assert ab["facts"]["cases_total"] == 63, f"autobuild 分母必须是 63(自有语料), got {ab['facts']['cases_total']}"
    assert orc["facts"]["cases_total"] == 142, f"oracle 分母必须是 142(套件), got {orc['facts']['cases_total']}"
    print(f"    ✓ 两维分母解耦:autobuild 40/63={ab['facts']['ready_rate']:.1%}, oracle 分母=142(不混用)")

    print("\n全部通过 ✅  —— 分数由机器从事实确定性折算,可复算、可单测")


if __name__ == "__main__":
    main()
