"""core.soak_report 真执行回归(main()+assert)。

soak_report 把多次 run 的 summary.json 聚合成稳定性报告(逐用例通过率、整体 stability、
资产使用、soak_runs 计数),质量门禁/资产健康消费它。此前覆盖仅 12%。本文件用真实
tmp 目录造多份 summary.json,在 run_tests.py 下真执行 aggregate/build/write 全链路。
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.soak_report import (
    aggregate_soak,
    build_soak_summary,
    write_soak,
    _classify,
    _ratio,
)


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _write_run(root: Path, run_id: str, cases: list[dict]) -> None:
    d = root / run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "summary.json").write_text(
        json.dumps({"run_id": run_id, "cases": cases}, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    # 1) _classify 四分类。
    _assert(_classify("PASS") == "pass", "pass 归一")
    _assert(_classify("partial") == "inconclusive", "partial→inconclusive")
    _assert(_classify("env_error") == "blocked", "env_error→blocked")
    _assert(_classify("whatever") == "fail", "未知→fail")
    _assert(_classify(None) == "fail", "None→fail")
    print("[1] _classify 四分类 ✓")

    # 2) _ratio 防除零。
    _assert(_ratio(3, 4) == 0.75, "正常比率")
    _assert(_ratio(1, 0) == 0.0, "除零保护")
    print("[2] _ratio 防除零 ✓")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # run1: 全过; run2: TC2 挂; run3: TC2 再挂。
        _write_run(root, "r1", [
            {"case_id": "TC1", "verdict": "pass"},
            {"case_id": "TC2", "verdict": "pass",
             "asset_usage": {"oracle": {"asset_id": "O1"}}},
        ])
        _write_run(root, "r2", [
            {"case_id": "TC1", "verdict": "pass"},
            {"case_id": "TC2", "verdict": "fail",
             "asset_usage": {"oracle": {"asset_id": "O1"}}},
        ])
        _write_run(root, "r3", [
            {"case_id": "TC1", "verdict": "pass"},
            {"case_id": "TC2", "verdict": "partial"},
        ])

        rep = aggregate_soak(root, min_runs=5)

        # 3) 基本聚合:3 run,仅 r1 全过。
        _assert(rep["soak_runs"] == 3, f"soak_runs=3, got {rep['soak_runs']}")
        _assert(rep["passed_runs"] == 1, f"只有 r1 全过, got {rep['passed_runs']}")
        _assert(rep["stability"] == _ratio(1, 3), "stability=1/3")
        _assert(rep["meets_min_runs"] is False, "3<5 不达 min_runs")
        _assert(rep["all_runs_passed"] is False, "非全部 run 过")
        print("[3] aggregate_soak 基本聚合 ✓")

        # 4) 逐用例通过率:TC1=1.0, TC2=1/3;per_case 按通过率升序(TC2 在前)。
        per = {c["case_id"]: c for c in rep["per_case"]}
        _assert(per["TC1"]["pass_rate"] == 1.0, "TC1 全过")
        _assert(per["TC2"]["pass_rate"] == _ratio(1, 3), "TC2 通过率 1/3")
        _assert(per["TC2"]["failures"] == 1 and per["TC2"]["inconclusive"] == 1, "TC2 1挂1不确定")
        _assert(rep["per_case"][0]["case_id"] == "TC2", "per_case 按通过率升序")
        print("[4] 逐用例通过率 + 升序 ✓")

        # 5) 资产使用聚合:O1 用了 2 次(r1过/r2挂)→ pass_rate 0.5。
        au = {a["asset_id"]: a for a in rep["asset_usage"]}
        _assert(au["O1"]["runs"] == 2, "O1 使用 2 次")
        _assert(au["O1"]["pass_rate"] == 0.5, "O1 通过率 0.5")
        print("[5] 资产使用聚合 ✓")

        # 6) build_soak_summary:总数/通过数/逐用例 verdict。
        summ = build_soak_summary(rep)
        _assert(summ["soak_runs"] == 3, "summary soak_runs")
        _assert(summ["total"] == 6, "6 条用例执行")
        _assert(summ["pass"] == 4, "4 次 pass(TC1×3+TC2×1)")
        scases = {c["case_id"]: c for c in summ["cases"]}
        _assert(scases["TC1"]["verdict"] == "PASS", "TC1 全过→PASS")
        _assert(scases["TC2"]["verdict"] == "FAIL", "TC2 未全过→FAIL")
        print("[6] build_soak_summary ✓")

        # 7) write_soak 落盘可读回。
        out = write_soak(rep, root / "out" / "soak.json")
        _assert(out.exists(), "soak 报告落盘")
        back = json.loads(out.read_text(encoding="utf-8"))
        _assert(back["soak_runs"] == 3, "读回一致")
        print("[7] write_soak 落盘读回 ✓")

        # 8) 空目录:soak_runs=0,stability=0,不崩。
        with tempfile.TemporaryDirectory() as empty:
            empty_rep = aggregate_soak(empty)
            _assert(empty_rep["soak_runs"] == 0, "空目录 0 run")
            _assert(empty_rep["stability"] == 0.0, "空目录 stability 0")
            _assert(empty_rep["all_runs_passed"] is False, "空目录非全过")
        print("[8] 空目录兜底 ✓")

    print("\nALL PASS · core.soak_report 稳定性聚合(classify/ratio/aggregate/build/write/空目录)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
