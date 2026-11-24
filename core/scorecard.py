"""计分卡(通用、零业务):把工具成熟度从"人写自评"变成"机器实测产出"。

9.5 分方案的 M1 核心:分数不再写在文档里,而是由本模块按确定性规则从真实运行
证据算出。每个维度一个纯函数,输入是已经采集好的事实(测试通过率、覆盖率、
自动建模覆盖率、oracle 覆盖率、demo 是否三源打通),输出 0~10 的分和依据。

本模块不执行测试、不读外部系统,只做"事实 → 分数"的确定性折算,便于单测与复算。
采集事实的脏活交给 scripts/scorecard.py(跑 run_tests、读 coverage、跑 demo)。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


def _clamp(value: float, low: float = 0.0, high: float = 10.0) -> float:
    return max(low, min(high, value))


def _round1(value: float) -> float:
    return round(value + 1e-9, 1)


@dataclass
class DimensionScore:
    name: str
    score: float
    weight: float
    basis: str
    facts: dict[str, Any] = field(default_factory=dict)


def score_runnability(tests_total: int, tests_passed: int) -> DimensionScore:
    """实际可运行性:非 UI 回归 + demo 由另一个维度覆盖,这里只看自测通过率。

    通过率线性映射到 0~10;0 条测试视为不可验证(0 分),避免"空仓假满分"。
    """
    rate = (tests_passed / tests_total) if tests_total else 0.0
    score = _clamp(rate * 10.0)
    return DimensionScore(
        name="runnability",
        score=_round1(score),
        weight=0.2,
        basis=f"自测通过率 {tests_passed}/{tests_total} = {rate:.1%}",
        facts={"tests_total": tests_total, "tests_passed": tests_passed, "pass_rate": round(rate, 4)},
    )


def score_coverage(coverage_pct: float) -> DimensionScore:
    """工程质量(覆盖率代理):以 80% 为满分锚点,线性折算。

    80%+ → 10;55%(旧门禁)→ 约 6.9。低覆盖率即使测试全绿也不给高分。
    """
    score = _clamp((coverage_pct / 80.0) * 10.0)
    return DimensionScore(
        name="coverage",
        score=_round1(score),
        weight=0.2,
        basis=f"分支覆盖率 {coverage_pct:.1f}%(满分锚点 80%)",
        facts={"coverage_pct": round(coverage_pct, 2), "anchor_pct": 80.0},
    )


def score_autobuild(cases_total: int, ready_true: int, zero_route: int = 0) -> DimensionScore:
    """无人值守成熟度(最大瓶颈):用例自动建模覆盖率。

    ready_true/total 为主(权重 0.7),其中"零人工路由直出"占比为加分(权重 0.3)。
    这是 6→9 的唯一路径,所以单独成维且权重最高。
    """
    ready_rate = (ready_true / cases_total) if cases_total else 0.0
    zero_route_rate = (zero_route / cases_total) if cases_total else 0.0
    blended = ready_rate * 0.7 + zero_route_rate * 0.3
    score = _clamp(blended * 10.0 / 0.85)  # 以 85% 综合覆盖为满分锚点
    return DimensionScore(
        name="autobuild",
        score=_round1(score),
        weight=0.35,
        basis=(f"自动建模覆盖 ready {ready_true}/{cases_total}={ready_rate:.1%}, "
               f"零人工路由 {zero_route}/{cases_total}={zero_route_rate:.1%}(满分锚点 85%)"),
        facts={"cases_total": cases_total, "ready_true": ready_true,
               "ready_rate": round(ready_rate, 4), "zero_route": zero_route,
               "zero_route_rate": round(zero_route_rate, 4)},
    )


def score_oracle(cases_with_oracle: int, cases_total: int, diff_mode: bool = False) -> DimensionScore:
    """判得准(oracle 覆盖 + 差异测试模式是否可用)。

    oracle 覆盖率以 80% 为满分锚点;差异测试模式可用再加 1 分封顶。
    """
    rate = (cases_with_oracle / cases_total) if cases_total else 0.0
    score = _clamp((rate / 0.8) * 9.0 + (1.0 if diff_mode else 0.0))
    return DimensionScore(
        name="oracle",
        score=_round1(score),
        weight=0.15,
        basis=(f"oracle 覆盖 {cases_with_oracle}/{cases_total}={rate:.1%}(锚点 80%)"
               f"{', 含差异测试模式' if diff_mode else ''}"),
        facts={"cases_with_oracle": cases_with_oracle, "cases_total": cases_total,
               "oracle_rate": round(rate, 4), "diff_mode": diff_mode},
    )


def score_demo(three_source_ok: bool) -> DimensionScore:
    """端到端三源打通:demo 是否 UI+API+DB 三边一致且 residue=0。布尔项。"""
    return DimensionScore(
        name="e2e_demo",
        score=10.0 if three_source_ok else 0.0,
        weight=0.1,
        basis=("demo 三源打通(UI+API+DB, residue=0)" if three_source_ok else "demo 未三源打通"),
        facts={"three_source_ok": bool(three_source_ok)},
    )


def aggregate(dimensions: list[DimensionScore]) -> dict[str, Any]:
    """按权重加权汇总为 0~10 综合分(权重自动归一化)。"""
    total_weight = sum(d.weight for d in dimensions) or 1.0
    overall = sum(d.score * d.weight for d in dimensions) / total_weight
    return {
        "overall": _round1(overall),
        "dimensions": [asdict(d) for d in dimensions],
        "weight_sum": round(total_weight, 4),
    }


def build_scorecard(
    *,
    tests_total: int,
    tests_passed: int,
    coverage_pct: float,
    cases_total: int,
    ready_true: int,
    zero_route: int = 0,
    cases_with_oracle: int = 0,
    diff_mode: bool = False,
    three_source_ok: bool = False,
) -> dict[str, Any]:
    """从采集好的事实产出完整计分卡(确定性、可单测、可复算)。"""
    dims = [
        score_runnability(tests_total, tests_passed),
        score_coverage(coverage_pct),
        score_autobuild(cases_total, ready_true, zero_route),
        score_oracle(cases_with_oracle, cases_total, diff_mode),
        score_demo(three_source_ok),
    ]
    return aggregate(dims)
