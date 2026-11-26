"""CP-1' 语义软门集成验证(离线、零业务):验 orchestrator 挂 checker 后的软门行为。
跑:python tests/test_orchestrator_softgate.py
"""
from __future__ import annotations

import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.orchestrator import run_case  # noqa: E402
from core.spec_checker import SpecChecker  # noqa: E402


# ── 桩子 Agent:离线产出合法产物,让三段都过闸(不起浏览器、不连库) ──

def _exec_spec(faithful: bool) -> dict:
    raw = {"steps": "create a new item and submit", "expected": "item created and listed"}
    if faithful:
        return {"exec_spec": {
            "case_id": "TC01", "title": "create item", "mode": "api",
            "verify_status": "human_verified", "raw": raw,
            "request": {"method": "POST", "url": "/api/items", "body": {"title": "x"}},
            "assertions": {"response": {"status": 200, "body": {"item": {"created": True}}}},
            "endpoints": ["/api/items"], "ui": {}, "steps": [],
        }}
    # 不忠实:结构合法(过 CP-1 结构门),但内容跟用例原意对不上——
    # 用例要 create/submit/item,spec 却指向无关的 ping 端点、断言也不沾边。
    # 结构门放行 → 进语义软门 → 被标『语义存疑·待人审』。
    return {"exec_spec": {
        "case_id": "TC01", "title": "status overview", "mode": "reconcile",
        "verify_status": "human_verified", "raw": raw,
        "request": {"method": "GET", "url": "/api/ping"},
        "assertions": {"response": {"status": 200, "body": {"health": "ok"}}},
        "endpoints": ["/api/ping"], "ui": {}, "steps": [],
    }}


class _SpecStub:
    def __init__(self, faithful): self._f = faithful
    def produce(self, stage, context): return _exec_spec(self._f)


class _ActionsStub:
    def produce(self, stage, context):
        return {"actions": {"status": "PASSED",
                            "steps": [{"index": 0, "kind": "click", "from_spec": "ui.actions[0]"}],
                            "evidence": ["shot.png"], "safety": {}}}


class _EvidenceStub:
    def produce(self, stage, context):
        return {"evidence": {"verdict": "pass", "sources": {"ui": True, "api": True, "db": False},
                            "evidence_sha256": {"shot.png": "abc"}, "reconcile": {"consistent": True}}}


def _agents(faithful):
    return {"spec": _SpecStub(faithful), "actions": _ActionsStub(), "evidence": _EvidenceStub()}


def _spec_outcome(result):
    return next(o for o in result.outcomes if o.stage == "spec")


def main():
    print("CP-1' 语义软门集成验证:\n")

    # 1) 软门不改过闸:不忠实 spec,语义软门标存疑,但 spec 段仍 PASS、流水线不停
    with tempfile.TemporaryDirectory() as d:
        result = run_case(_agents(faithful=False), d, "TC01",
                          checker=SpecChecker(min_coverage=0.5))
        so = _spec_outcome(result)
        assert so.verdict == "pass", f"软门绝不能改 spec 过闸结论,实得 {so.verdict}"
        assert result.completed, "软门绝不能停流水线"
        assert any("语义存疑" in r for r in so.reasons), so.reasons
        # 落了 spec_review 旁路产物
        review_path = os.path.join(d, "TC01", "artifacts", "spec_review.json")
        assert os.path.isfile(review_path), "应落 spec_review.json 候选产物"
        print("    ✓ 不忠实 spec:软门标『语义存疑·待人审』,但 spec 仍 pass、三段跑完(软门不阻断)")

    # 2) 忠实 spec:软门判 semantic_ok,不附存疑提示
    with tempfile.TemporaryDirectory() as d:
        result = run_case(_agents(faithful=True), d, "TC01",
                          checker=SpecChecker(min_coverage=0.4))
        so = _spec_outcome(result)
        assert so.verdict == "pass" and result.completed
        assert not any("语义存疑" in r for r in so.reasons), so.reasons
        print("    ✓ 忠实 spec:软门 semantic_ok,无存疑标注,正常过闸")

    # 3) 不开 checker:行为与改造前完全一致(回归保护)
    with tempfile.TemporaryDirectory() as d:
        result = run_case(_agents(faithful=False), d, "TC01")  # checker=None
        so = _spec_outcome(result)
        assert so.verdict == "pass" and result.completed
        assert not any("语义" in r for r in so.reasons), "不开 checker 不应有任何语义标注"
        assert not os.path.isfile(os.path.join(d, "TC01", "artifacts", "spec_review.json"))
        print("    ✓ 不开 checker:零语义副作用,与改造前一致(回归保护)")

    # 4) verify_status 不被软门触碰(人审门保留)
    with tempfile.TemporaryDirectory() as d:
        run_case(_agents(faithful=False), d, "TC01", checker=SpecChecker())
        import json
        spec = json.loads(open(os.path.join(d, "TC01", "artifacts", "spec.json"),
                               encoding="utf-8").read())
        assert spec["exec_spec"]["verify_status"] == "human_verified", "软门绝不改 exec_spec"
        print("    ✓ 软门只读 exec_spec:verify_status 等字段原样不动(挑错不改产物)")

    print("\n全部通过 ✅  —— CP-1' 语义软门:不改过闸/不停流水线/落候选/标待人审,挑错不改产物")


if __name__ == "__main__":
    main()
