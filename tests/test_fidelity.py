"""离线单测:core.fidelity 打分器(纯函数,无真网、无业务词)。
验:满分链、断链扣分、维度不适用的归一、分档、权重覆盖。
跑:python tests/test_fidelity.py
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.fidelity import score_case, DEFAULT_WEIGHTS


def _ok(reason=""): return {"ok": True, "reason": reason}
def _no(reason=""): return {"ok": False, "reason": reason}
def _na(reason=""): return {"ok": None, "reason": reason}


def test_full_chain_is_100_grade_a():
    f = score_case({
        "ui_driven": _ok(), "api_layer": _ok(), "db_layer": _ok(),
        "consistency": _ok(), "evidence": _ok(),
    })
    assert f.score == 100, f.score
    assert f.grade == "A", f.grade


def test_broken_ui_drive_drops_40():
    # 页面没驱动(接口建单),其余都对 → 丢 ui_driven 的 40 分 → 60
    f = score_case({
        "ui_driven": _no("录到的接口往返里没有该写调用"), "api_layer": _ok(),
        "db_layer": _ok(), "consistency": _ok(), "evidence": _ok(),
    })
    assert f.score == 60, f.score
    assert f.grade == "C", f.grade
    d = {x.name: x for x in f.dims}
    assert d["ui_driven"].ok is False and d["ui_driven"].got == 0
    assert "没有该写调用" in d["ui_driven"].reason


def test_api_db_class_normalizes_over_applicable():
    # 纯接口+库类:ui_driven 不适用 → 从分母剔除。api+db+一致 全对 → 100(不因缺 UI 被压低)
    f = score_case({
        "ui_driven": _na("接口+库类,不计 UI 维度"), "api_layer": _ok(),
        "db_layer": _ok(), "consistency": _ok(), "evidence": _ok(),
    })
    assert f.score == 100, f.score
    d = {x.name: x for x in f.dims}
    assert d["ui_driven"].applicable is False
    assert d["ui_driven"].got == 0 and d["ui_driven"].max == 40


def test_api_db_class_partial():
    # 接口+库类:库层挂了 → 适用维度 api(20)+db(20)+一致(10)+证据(10)=60,得 api+一致+证据=40 → 40/60≈67
    f = score_case({
        "ui_driven": _na(), "api_layer": _ok(), "db_layer": _no("库里未查到标记"),
        "consistency": _ok(), "evidence": _ok(),
    })
    assert f.score == round(100 * 40 / 60), f.score   # 67


def test_no_applicable_is_zero_lowest_grade():
    f = score_case({k: _na() for k in DEFAULT_WEIGHTS})
    assert f.score == 0 and f.grade == "D", (f.score, f.grade)


def test_weights_override():
    # 把 ui_driven 压到 10、api 抬到 50:ui 挂、其余全对 → (50+20+10+10)/(10+50+20+10+10)=90/100=90 → A
    w = {"ui_driven": 10, "api_layer": 50, "db_layer": 20, "consistency": 10, "evidence": 10}
    f = score_case({
        "ui_driven": _no(), "api_layer": _ok(), "db_layer": _ok(),
        "consistency": _ok(), "evidence": _ok(),
    }, weights=w)
    assert f.score == 90 and f.grade == "A", (f.score, f.grade)


def test_required_db_leg_missing_is_penalized():
    # 写用例声明 require_db,但没查库(db_ok=None)→ 库腿判"缺失=未达标",不再白拿满分。
    from core.fidelity import build_dims
    dims = build_dims(expect_ui=False, ui_triggered=None, api_ok=True, db_ok=None,
                      consistent=None, evidence_ok=True, require_api=True, require_db=True)
    assert dims["db_layer"]["ok"] is False, dims["db_layer"]
    assert "这一腿缺失" in dims["db_layer"]["reason"]
    f = score_case(dims)
    # 适用:api(20,ok)+db(20,缺失→0)+evidence(10,ok)=30/50 → 60 → C
    assert f.score == 60 and f.grade == "C", (f.score, f.grade)


def test_required_db_leg_not_required_stays_na():
    # 纯前端校验类:require_db=False,db_ok=None → 库腿仍不适用(不冤枉扣分)。
    from core.fidelity import build_dims
    dims = build_dims(expect_ui=True, ui_triggered=True, api_ok=None, db_ok=None,
                      consistent=None, evidence_ok=True, require_api=False, require_db=False)
    assert dims["db_layer"]["ok"] is None
    f = score_case(dims)
    # 适用:ui(40,ok)+evidence(10,ok)=50/50 → 100
    assert f.score == 100, f.score


def test_custom_bands():
    f = score_case({"api_layer": _ok(), "db_layer": _no()},
                   grade_bands=[("优", 80), ("良", 50), ("差", 0)])
    # 适用 api(20)+db(20)=40,得 20 → 50 → "良"
    assert f.score == 50 and f.grade == "良", (f.score, f.grade)


def test_tri_source_consistent_true():
    # 三源做实:页面驱动 + 标记在写请求体 + 库断言命中 → 一致
    from core.fidelity import tri_source_consistent
    ok, src = tri_source_consistent("AUTOTEST_X", {"requestTitle": "AUTOTEST_X", "n": 1}, True, True)
    assert ok is True
    assert src == {"page_drove": True, "marker_in_request": True, "db_matched": True}


def test_tri_source_marker_not_in_request():
    # 页面驱动了、库也命中,但写请求体里没有这个标记(接口打的是另一张单)→ 不一致
    from core.fidelity import tri_source_consistent
    ok, src = tri_source_consistent("AUTOTEST_X", {"requestTitle": "别的单"}, True, True)
    assert ok is False and src["marker_in_request"] is False


def test_tri_source_missing_a_leg():
    from core.fidelity import tri_source_consistent
    # 没页面驱动
    ok, _ = tri_source_consistent("M", {"t": "M"}, False, True); assert ok is False
    # 库断言没命中
    ok, _ = tri_source_consistent("M", {"t": "M"}, True, False); assert ok is False
    # 空请求体
    ok, s = tri_source_consistent("M", None, True, True); assert ok is False and s["marker_in_request"] is False


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n✅ fidelity 全通过({len(tests)} 项)")


if __name__ == "__main__":
    main()
