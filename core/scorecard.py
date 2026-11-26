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


def score_oracle(cases_with_oracle: int, cases_total: int, diff_mode: bool = False,
                 cases_partial: int = 0) -> DimensionScore:
    """判得准(oracle 覆盖 + 差异测试模式是否可用)。

    有效覆盖 = ready 全权 + partial 半权。partial 指用例已有结构化断言且正确绑定了
    『部分』证明层(如确定性只抽出 api 层,ui/db 证明待补)——比纯散文(blocked)可信,
    但不如三层齐全(ready),故按半权诚实计入,不是降标准也不是凑数。
    有效覆盖率以 80% 为满分锚点;差异测试模式可用再加 1 分封顶。
    """
    effective = cases_with_oracle + 0.5 * cases_partial
    rate = (effective / cases_total) if cases_total else 0.0
    score = _clamp((rate / 0.8) * 9.0 + (1.0 if diff_mode else 0.0))
    partial_note = f"(+{cases_partial} partial 半权)" if cases_partial else ""
    return DimensionScore(
        name="oracle",
        score=_round1(score),
        weight=0.15,
        basis=(f"oracle 覆盖 ready {cases_with_oracle}+partial {cases_partial} "
               f"/{cases_total}={rate:.1%}{partial_note}(锚点 80%)"
               f"{', 含差异测试模式' if diff_mode else ''}"),
        facts={"cases_with_oracle": cases_with_oracle, "cases_partial": cases_partial,
               "cases_total": cases_total, "effective_cases": round(effective, 1),
               "oracle_rate": round(rate, 4), "diff_mode": diff_mode},
    )


def score_generalization(systems: list[dict[str, Any]], anchor: int = 3) -> DimensionScore:
    """跨系统泛化(用户初衷:工具要能在别的系统上也自驱做 UI 自动化,不是只过一张固定考卷)。

    输入是每个"真实异构系统"的机器判定事实(采集脏活在 scripts 层,这里不认任何业务):
      - self_driven=True : 管线在该系统的真实流量上既自动发现了接口目录(catalog),
                           又建出了就绪模型(readiness)——真正自驱跑通,全权计 1。
      - partial=True     : 只到了接口发现这一步(catalog 可从真实流量机器抽出),
                           但还没建 readiness——半权计 0.5(诚实反映只走了一半,不是 0 也不冒充跑通)。
    有效系统数 = Σ(self_driven) + 0.5·Σ(partial 且非 self_driven);以 anchor 个不同真实
    异构系统为满分锚点(证明不是对单一系统过拟合)。无任何系统=0,避免"单系统假泛化"。
    """
    full = sum(1 for s in systems if s.get("self_driven"))
    partial = sum(1 for s in systems if s.get("partial") and not s.get("self_driven"))
    effective = full + 0.5 * partial
    rate = (effective / anchor) if anchor else 0.0
    score = _clamp(rate * 10.0)
    ids_full = [s.get("id") for s in systems if s.get("self_driven")]
    ids_part = [s.get("id") for s in systems if s.get("partial") and not s.get("self_driven")]
    return DimensionScore(
        name="generalization",
        score=_round1(score),
        weight=0.1,
        basis=(f"自驱跑通 {full} 个 + 半通 {partial} 个 = 有效 {effective:g}/{anchor} 个真实异构系统"
               f"(满分锚点 {anchor} 个){'；全通: ' + ','.join(str(x) for x in ids_full) if ids_full else ''}"
               f"{'；半通: ' + ','.join(str(x) for x in ids_part) if ids_part else ''}"),
        facts={"systems_full": full, "systems_partial": partial,
               "effective_systems": round(effective, 1), "anchor": anchor,
               "ids_full": ids_full, "ids_partial": ids_part},
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
    cases_partial: int = 0,
    three_source_ok: bool = False,
    oracle_total: int | None = None,
    systems: list[dict[str, Any]] | None = None,
    generalization_anchor: int = 3,
) -> dict[str, Any]:
    """从采集好的事实产出完整计分卡(确定性、可单测、可复算)。

    cases_total   : autobuild 维的分母——工具实际自动建模过的那套语料的用例总数。
    oracle_total  : oracle 维的分母——被评估套件的用例总数;缺省退回 cases_total。
    两维分母必须各用各的语料,不可混用(否则分子来自语料甲、分母来自语料乙,
    autobuild 会被一张固定考卷的规模绑架,量不出跨语料/跨系统的真实建模率)。
    systems       : 跨系统泛化维的事实——每个真实异构系统一条 {id, self_driven, partial};
                    缺省空列表(=0 分,不假装泛化)。
    """
    o_total = oracle_total if oracle_total is not None else cases_total
    dims = [
        score_runnability(tests_total, tests_passed),
        score_coverage(coverage_pct),
        score_autobuild(cases_total, ready_true, zero_route),
        score_oracle(cases_with_oracle, o_total, diff_mode, cases_partial),
        score_demo(three_source_ok),
        score_generalization(systems or [], anchor=generalization_anchor),
    ]
    return aggregate(dims)
