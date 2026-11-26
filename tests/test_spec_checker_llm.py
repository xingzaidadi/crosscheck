"""CP-1' 档位B 验证(离线、零业务、桩 provider 非真网络):
档位A 词面盲区 → 档位B 语义救回 → 快照冻结可复现铁证 → 降级不变 → 软门不越界。
跑:python tests/test_spec_checker_llm.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.spec_checker import (  # noqa: E402
    REVIEW_ARTIFACT, STATUS_OK, STATUS_REVIEW, SpecChecker,
    freeze_review, review_from_snapshot, review_spec, _snapshot_index,
)


def _spec_synonym():
    """构造词面零重合的中性同义对:用例说 "下单/checkout",spec 操作叫 "提交订单/placeOrder"。
    两组词 tokens 无交集 → 档位A 必判覆盖不足,但语义其实忠实(档位B 该救回)。
    零业务:用通用中性词 checkout↔placeOrder、submit↔dispatch,不内置业务词典。
    """
    return {
        "case_id": "TC-SYN",
        "title": "checkout flow",
        "mode": "ui",
        "raw": {"steps": "user does checkout and submit", "expected": "checkout confirmed"},
        "request": {},
        "assertions": {"response": {"placeOrder": {"dispatched": True}}},
        "ui": {"instruction": "placeOrder then dispatch", "actions": [{"kind": "placeOrder"}]},
        "endpoints": ["/placeOrder"],
        "steps": [],
    }


class _Ctx:
    def __init__(self, exec_spec):
        self._spec = exec_spec

    def upstream_artifact(self, stage):
        return self._spec


class _StubProvider:
    """桩 provider:不碰网络,带调用计数器——用于证明快照判定绝不调模型。"""
    def __init__(self, faithful=True, reasons=None, gaps=None):
        self.calls = 0
        self._faithful = faithful
        self._reasons = reasons or []
        self._gaps = gaps or []

    def __call__(self, **context):
        self.calls += 1
        return {
            "status": STATUS_OK if self._faithful else STATUS_REVIEW,
            "faithful": self._faithful,
            "reasons": list(self._reasons),
            "semantic_gaps": list(self._gaps),
        }


def main():
    print("CP-1' 档位B(LLM 语义复核 + 快照冻结可复现)验证:\n")

    # 1) 档位A 盲区复现:词面零重合的同义对 → 档位A 误判覆盖不足(needs_human_review)
    a = review_spec(_spec_synonym(), min_coverage=0.5)
    assert a["tier"] == "lexical", a
    assert a["status"] == STATUS_REVIEW, a
    assert any("覆盖不足" in r for r in a["reasons"]), a["reasons"]
    print(f"    ✓ 档位A 盲区真实:同义词面零重合 → {a['status']}(coverage={a['coverage']:.0%}),语义忠实却被误报")

    # 2) 档位B 桩修正:注入 faithful=True 的桩 provider → produce 救回 semantic_ok、tier=llm
    stub_ok = _StubProvider(faithful=True, reasons=["语义忠实:下单=提交订单"])
    checker_llm = SpecChecker(min_coverage=0.5, llm=stub_ok)
    out = checker_llm.produce("spec", _Ctx(_spec_synonym()))
    review = out[REVIEW_ARTIFACT]
    assert review["tier"] == "llm", review
    assert review["status"] == STATUS_OK, review
    assert review["faithful"] is True, review
    assert stub_ok.calls == 1, f"实时档位B 应恰调一次 provider,实际 {stub_ok.calls}"
    # 档位A 的覆盖证据仍保留(coverage/missing 作为人审依据)
    assert "coverage" in review and "missing" in review, review
    print(f"    ✓ 档位B 救回:语义层判 {review['status']}(tier=llm),档位A 覆盖证据保留")

    # 3) 快照可复现铁证:冻结一次 → 从快照读回两次逐位一致,且全程不调 provider
    frozen = freeze_review("TC-SYN", review)
    snapshot = {"reviews": [frozen]}
    snap_index = _snapshot_index(snapshot)
    r1 = review_from_snapshot(_spec_synonym(), snap_index, min_coverage=0.5)
    r2 = review_from_snapshot(_spec_synonym(), snap_index, min_coverage=0.5)
    assert r1 == r2, "同一快照两次判定必须逐位一致(可复现铁律)"
    assert r1["tier"] == "llm" and r1["status"] == STATUS_OK, r1

    # 用带计数器的 provider 装到 SpecChecker,走 snapshot 分支 → provider 调用数必须==0
    guard = _StubProvider(faithful=False)   # 故意返回相反结论;若被调用会污染,但快照路径绝不调它
    checker_snap = SpecChecker(min_coverage=0.5, llm=guard, snapshot=snapshot)
    s1 = checker_snap.produce("spec", _Ctx(_spec_synonym()))[REVIEW_ARTIFACT]
    s2 = checker_snap.produce("spec", _Ctx(_spec_synonym()))[REVIEW_ARTIFACT]
    assert s1 == s2, "快照判定必须确定性"
    assert s1["status"] == STATUS_OK, f"应读回冻结的 semantic_ok,而非 provider 的相反结论:{s1}"
    assert guard.calls == 0, f"快照在场时绝不调模型,实际调了 {guard.calls} 次(破可复现铁律)"
    print(f"    ✓ 快照可复现:两次读回逐位一致、snapshot 优先于 llm、provider 调用计数=={guard.calls}")

    # 4) 快照缺该 case → 降级纯档位A(不伪造档位B 结论)
    other = review_from_snapshot(_spec_synonym(), _snapshot_index({"reviews": []}), min_coverage=0.5)
    assert other["tier"] == "lexical", other
    assert other["status"] == STATUS_REVIEW, other
    print("    ✓ 快照缺 case → 诚实降级档位A(tier=lexical),不伪造语义结论")

    # 5) 降级不变:无 llm、无 snapshot → 档位A,行为与现状逐位一致
    plain = SpecChecker(min_coverage=0.5)
    base = plain.produce("spec", _Ctx(_spec_synonym()))[REVIEW_ARTIFACT]
    assert base == review_spec(_spec_synonym(), min_coverage=0.5), base
    assert base["tier"] == "lexical", base
    # 遗留 "placeholder" 字符串不得被当真 provider(仍降级档位A)
    legacy = SpecChecker(min_coverage=0.5, llm="placeholder")
    legacy_out = legacy.produce("spec", _Ctx(_spec_synonym()))[REVIEW_ARTIFACT]
    assert legacy_out["tier"] == "lexical", legacy_out
    print("    ✓ 降级不变:无 llm/snapshot(含遗留 placeholder 字符串)→ 档位A,逐位同现状")

    # 6) 软门不越界:档位B / 快照 两条路径的 produce 产物都只含 spec_review 键
    assert set(checker_llm.produce("spec", _Ctx(_spec_synonym())).keys()) == {REVIEW_ARTIFACT}
    assert set(checker_snap.produce("spec", _Ctx(_spec_synonym())).keys()) == {REVIEW_ARTIFACT}
    print(f"    ✓ 软门不越界:档位B/快照 produce 仍只产 {REVIEW_ARTIFACT},不碰 exec_spec")

    # 7) provider 抛异常 → 降级档位A(软门第二档不得拖垮主流程)
    class _Boom:
        def __call__(self, **kw):
            raise RuntimeError("provider down")
    boom = SpecChecker(min_coverage=0.5, llm=_Boom())
    boom_out = boom.produce("spec", _Ctx(_spec_synonym()))[REVIEW_ARTIFACT]
    assert boom_out["tier"] == "lexical", boom_out
    print("    ✓ provider 异常 → 降级档位A,主流程不受拖累")

    print("\n全部通过 ✅  —— CP-1' 档位B:语义救盲区、快照冻结可复现、默认降级、软门不越界、零业务")


if __name__ == "__main__":
    main()
