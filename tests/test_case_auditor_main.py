"""core.case_auditor 真执行回归(main()+assert)。

case_auditor 是确定性用例质量/就绪审计(schema/intent/role/traceability/模糊词/
v2 前置与 oracle/重复 case_id → ready 判定 + 扣分)。此前覆盖仅 9%。本文件在
run_tests.py 下真执行各 issue 分支与评分。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.case_auditor import audit_case, audit_cases, AMBIGUOUS


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _kinds(report):
    return {i["kind"] for i in report["issues"]}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    # 1) 完整 v1 用例:无 error → ready=True, score=100。
    good = {"case_id": "TC1", "intent": {"under_test": "下单"},
            "actors": ["buyer"], "traceability": "REQ-1",
            "title": "下单后生成订单", "expected": "订单号非空"}
    r = audit_case(good)
    _assert(r["ready"] is True, f"完整用例应 ready, issues={r['issues']}")
    _assert(r["score"] == 100, f"无问题 score=100, got {r['score']}")
    print("[1] 完整 v1 用例 ready ✓")

    # 2) 缺 intent.under_test + 缺 actor → 两个 error,ready=False。
    r2 = audit_case({"case_id": "TC2", "traceability": "X"})
    _assert("intent" in _kinds(r2), "缺 intent 报错")
    _assert("role" in _kinds(r2), "缺 actor 报错")
    _assert(r2["ready"] is False, "有 error 不 ready")
    _assert(r2["score"] == 100 - 2 * 25, "两个 error 扣 50")
    print("[2] 缺 intent/actor → error ✓")

    # 3) 缺 traceability → warning(不致命,仍可 ready)。
    r3 = audit_case({"case_id": "TC3", "intent": {"under_test": "x"}, "actor": "u"})
    _assert("source" in _kinds(r3), "缺 traceability 报 warning")
    srcissue = next(i for i in r3["issues"] if i["kind"] == "source")
    _assert(srcissue["severity"] == "warning", "traceability 是 warning")
    _assert(r3["ready"] is True, "只有 warning 仍 ready")
    print("[3] 缺 traceability → warning 不阻断 ✓")

    # 4) open_questions 每条 → error。
    r4 = audit_case({"case_id": "TC4", "intent": {"under_test": "x"}, "actor": "u",
                     "traceability": "t", "open_questions": ["登录方式未定", "环境未知"]})
    oq = [i for i in r4["issues"] if i["kind"] == "open_question"]
    _assert(len(oq) == 2, "两条 open_question 两个 error")
    _assert(r4["ready"] is False, "open_question 阻断 ready")
    print("[4] open_questions → error ✓")

    # 5) 模糊词 → warning。
    _assert(AMBIGUOUS, "模糊词表非空")
    r5 = audit_case({"case_id": "TC5", "intent": {"under_test": "x"}, "actor": "u",
                     "traceability": "t", "expected": "页面正常显示即可"})
    _assert("ambiguity" in _kinds(r5), "命中模糊词报 warning")
    print("[5] 模糊词 → warning ✓")

    # 6) v2:缺 oracle + precondition 无 object → error。
    v2bad = {"case_id": "TC6", "schema_version": 2,
             "intent": {"under_test": "x"}, "actor": "u", "traceability": "t",
             "preconditions": [{"note": "无 object"}]}
    r6 = audit_case(v2bad)
    _assert("oracle" in _kinds(r6), "v2 缺 oracle 报错")
    _assert("precondition" in _kinds(r6), "precondition 缺 object 报错")
    _assert(r6["ready"] is False, "v2 缺失阻断")
    print("[6] v2 precondition/oracle 校验 ✓")

    # 7) audit_cases:重复 case_id → 后者标 duplicate+不 ready;total/ready 统计。
    batch = audit_cases([good, dict(good)])  # 同 case_id TC1 两次
    _assert(batch["total"] == 2, "总数 2")
    _assert(batch["ready"] == 1, "重复的那条不计入 ready")
    dup = batch["cases"][1]
    _assert("duplicate" in _kinds(dup), "第二条标 duplicate")
    _assert(dup["ready"] is False, "重复 case_id 不 ready")
    print("[7] audit_cases 重复 case_id 检测 ✓")

    # 8) score 不为负(大量 error 时下限 0)。
    r8 = audit_case({"case_id": "TC8", "schema_version": 2})  # 几乎全缺
    _assert(r8["score"] >= 0, "score 下限 0")
    _assert(r8["ready"] is False, "全缺不 ready")
    print("[8] score 下限 0 ✓")

    print("\nALL PASS · core.case_auditor 用例审计(intent/role/trace/open_q/模糊/v2/重复/评分)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
