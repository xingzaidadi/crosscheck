"""product_readiness 分支覆盖(离线、零业务):复杂度分级 + 成熟度打分 + 阻断项。

run_tests.py 把 test_*.py 当脚本跑(returncode==0 即过),纯 pytest 风格不贡献覆盖。
本文件 main()+assert 真实执行,补 assess_case_complexity 的 L0–L4 全档、_run_metrics 的
有/无 run_report 与 cases 回退、assess_product_readiness 的维度加权/成熟度 M0–M4/阻断项分支。
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.product_readiness import (  # noqa: E402
    assess_case_complexity, assess_product_readiness, write_product_readiness,
    _run_metrics, _ratio, _required_layers,
)


def test_complexity_levels_l0_to_l4():
    # L0:无 layers、无 action
    assert assess_case_complexity({"case_id": "c"})["level"] == "L0"
    # L1:有 action 但无状态依赖/多层
    assert assess_case_complexity({"case_id": "c", "action": "click"})["level"] == "L1"
    # L2:>=2 层
    assert assess_case_complexity(
        {"case_id": "c", "layers": {"required": ["ui", "api"]}})["level"] == "L2"
    # L2:单层但有状态依赖(前置条件)
    assert assess_case_complexity(
        {"case_id": "c", "layers": {"required": ["ui"]},
         "preconditions": ["登录"]})["level"] == "L2"
    # L3:跨系统(>=3 层)+ 状态依赖
    l3 = assess_case_complexity({"case_id": "c",
        "layers": {"required": ["ui", "api", "db"]}, "preconditions": ["seed"]})
    assert l3["level"] == "L3", l3
    assert l3["dimensions"]["cross_system"] is True
    # L4:高风险 + (跨系统或状态依赖)
    l4 = assess_case_complexity({"case_id": "c",
        "layers": {"required": ["ui", "api", "db"]},
        "preconditions": ["seed"], "notes": "幂等 并发 核心交易"})
    assert l4["level"] == "L4", l4
    assert l4["dimensions"]["high_risk"] is True
    print("  ✓ complexity:L0/L1/L2/L3/L4 五档,高风险+跨系统升顶档")


def test_complexity_async_and_event_dimensions():
    # event 层 → cross_system 且 async_dependency
    c = assess_case_complexity({"case_id": "c", "layers": {"required": ["event"]}})
    assert c["dimensions"]["cross_system"] is True
    assert c["dimensions"]["async_dependency"] is True
    # wait 触发 async
    c2 = assess_case_complexity({"case_id": "c", "wait": {"poll": 3}})
    assert c2["dimensions"]["async_dependency"] is True
    # _required_layers 容错:layers 非 dict → 空集
    assert _required_layers({"layers": ["x"]}) == set()
    print("  ✓ complexity:event/wait 触发异步与跨系统维度,layers 非 dict 容错")


def test_run_metrics_variants():
    # 无 run_report → 稳定性 0、inconclusive 1、无证据
    m = _run_metrics(None)
    assert m == {"run_stability": 0.0, "inconclusive_rate": 1.0, "has_run_evidence": 0.0}
    # 显式字段
    m = _run_metrics({"total": 10, "passed": 9, "inconclusive": 1})
    assert m["run_stability"] == 0.9 and m["inconclusive_rate"] == 0.1
    assert m["has_run_evidence"] == 1.0
    # total<=0 时从 cases 列表回退统计 + soak 加成
    rep = {"soak_runs": 5, "cases": [{"status": "PASS"}] * 20 + [{"status": "unknown"}]}
    m = _run_metrics(rep)
    # 20/21≈0.952 ≥0.95 且 soak>=5 → +0.05 封顶 1.0
    assert m["run_stability"] == 1.0, m["run_stability"]
    assert m["has_run_evidence"] == 1.0
    assert _ratio(1, 0) == 0.0            # 分母 0 保护
    print("  ✓ _run_metrics:无报告/显式/cases回退/soak加成/分母0 全覆盖")


def _ready_case(cid):
    return {"case_id": cid, "status": "ready",
            "approval": {"reviewer": "qa", "approved_at": "t"},
            "execution": {"mode": "read"},
            "evidence": {"api": "ok"}, "assertions": {"api": [{"id": "a"}]},
            "layers": {"required": ["api"]}}


def test_product_readiness_empty_suite_is_vacuous_m1():
    # 空套件:preparation 真空满分 1.0 → score 15.0 → M1(非 M0);仍 NOT_READY、缺外部证据
    rep = assess_product_readiness({"suite_id": "s"}, [])
    assert rep["maturity"]["level"] == "M1"
    assert rep["maturity"]["score"] == 15.0
    assert rep["maturity"]["dimensions"]["preparation"] == 1.0   # 无前置可准备=真空100%
    assert rep["production_readiness"] == "NOT_READY"            # M1 不入 READY
    assert any(b["type"] == "external_evidence_missing" for b in rep["blockers"])
    assert rep["total_cases"] == 0
    print("  ✓ product_readiness:空套件→M1(preparation真空满分)/NOT_READY/缺外部证据")


def test_product_readiness_blockers_surface():
    # 一条未就绪用例 → readiness<1 触发 readiness_blocked;无 run_report 触发外部证据缺
    cases = [{"case_id": "c1", "status": "draft"}]
    rep = assess_product_readiness({"suite_id": "s"}, cases)
    types = {b["type"] for b in rep["blockers"]}
    assert "readiness_blocked" in types
    assert "external_evidence_missing" in types
    # next_actions 取前 5 条阻断动作
    assert rep["next_actions"] == [b["action"] for b in rep["blockers"][:5]]
    print("  ✓ product_readiness:未就绪→readiness_blocked,动作清单取前5")


def test_product_readiness_maturity_climbs_with_run_evidence():
    # 全就绪 + 高稳定 run_report,inconclusive 低 → 分数上行,成熟度随证据升
    cases = [_ready_case(f"c{i}") for i in range(10)]
    run = {"total": 10, "passed": 10, "inconclusive": 0, "soak_runs": 5}
    rep = assess_product_readiness({"suite_id": "s"}, cases, run_report=run)
    dims = rep["maturity"]["dimensions"]
    assert dims["readiness"] == 1.0 and dims["approval"] == 1.0
    assert dims["run_stability"] == 1.0 and dims["has_run_evidence"] == 1.0
    assert dims["inconclusive_rate"] == 0.0
    # 带 run 证据时成熟度不应停在 M0/M1(有稳定运行证据)
    assert rep["maturity"]["level"] in {"M2", "M3", "M4"}, rep["maturity"]
    print(f"  ✓ product_readiness:全就绪+稳定 soak→{rep['maturity']['level']}(score={rep['maturity']['score']})")


def test_product_readiness_inconclusive_blocker():
    cases = [_ready_case(f"c{i}") for i in range(10)]
    # inconclusive 率 >10% → evidence_blocked
    run = {"total": 10, "passed": 7, "inconclusive": 3}
    rep = assess_product_readiness({"suite_id": "s"}, cases, run_report=run)
    assert any(b["type"] == "evidence_blocked" for b in rep["blockers"]), rep["blockers"]
    print("  ✓ product_readiness:INCONCLUSIVE 率>10%→evidence_blocked")


def test_write_product_readiness_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "nested" / "product-readiness.json"
        p = write_product_readiness({"schema_version": 1, "maturity": {"level": "M0"}}, out)
        assert p.is_file()
        assert json.loads(p.read_text(encoding="utf-8"))["maturity"]["level"] == "M0"
    print("  ✓ write_product_readiness 落盘(自建父目录,可回读)")


def main():
    test_complexity_levels_l0_to_l4()
    test_complexity_async_and_event_dimensions()
    test_run_metrics_variants()
    test_product_readiness_empty_suite_is_vacuous_m1()
    test_product_readiness_blockers_surface()
    test_product_readiness_maturity_climbs_with_run_evidence()
    test_product_readiness_inconclusive_blocker()
    test_write_product_readiness_roundtrip()
    print("\n全部通过 ✅  —— product_readiness 分支覆盖(复杂度五档/成熟度/阻断项)")


if __name__ == "__main__":
    main()
