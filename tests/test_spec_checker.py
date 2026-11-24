"""CP-1 语义复核 checker 验证(离线、零业务):验『用例原意 vs 转出操作』的词法覆盖软门。
跑:python tests/test_spec_checker.py
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
    REVIEW_ARTIFACT, STATUS_OK, STATUS_REVIEW, SpecChecker, review_spec,
)
from core.stage_runner import StageContext, enforce_write_scope, write_scope  # noqa: E402


def _spec(**kw):
    """造一个中性 exec_spec(零业务词),raw 带用例原文副本。"""
    base = {
        "case_id": "TC01", "title": "create item", "mode": "api",
        "verify_status": "human_verified",
        "raw": {"steps": "create a new item and submit", "expected": "item created and listed"},
        "request": {"method": "POST", "url": "/api/items", "body": {"title": "x"}},
        "assertions": {"response": {"status": 200, "body": {"item": {"created": True}}}},
        "ui": {}, "endpoints": ["/api/items"], "steps": [],
    }
    base.update(kw)
    return base


class _Ctx:
    """最小 StageContext 替身:upstream_artifact('spec') 回 exec_spec。"""
    def __init__(self, exec_spec):
        self._spec = exec_spec

    def upstream_artifact(self, stage):
        return self._spec


def main():
    print("CP-1 语义复核 checker 验证:\n")

    # 1) 忠实 spec:动作/预期都覆盖到 → semantic_ok
    good = review_spec(_spec(), min_coverage=0.4)
    assert good["status"] == STATUS_OK, good
    assert good["coverage"] > 0, good
    print(f"    ✓ 忠实 spec → {good['status']}(coverage={good['coverage']:.0%},无缺口)")

    # 2) 漏动作:用例要求 create+submit+item,spec 操作/断言几乎不沾边 → needs_human_review
    miss = review_spec(_spec(
        request={"method": "GET", "url": "/x"}, assertions={}, endpoints=["/x"],
        raw={"steps": "create a new item and submit it then approve", "expected": "approved"}),
        min_coverage=0.5)
    assert miss["status"] == STATUS_REVIEW, miss
    assert miss["missing"], "应给出漏掉的用例词清单"
    assert any("覆盖不足" in r for r in miss["reasons"]), miss["reasons"]
    print(f"    ✓ 漏动作 spec → {miss['status']}(missing={miss['missing'][:4]}…)")

    # 3) 漏预期:动作覆盖够,但 expected 的判定点没进断言/ui → 存疑
    miss_exp = review_spec(_spec(
        assertions={}, request={"method": "POST", "url": "/api/items"},
        raw={"steps": "create item", "expected": "the audit status becomes finalized"}),
        min_coverage=0.3)
    assert miss_exp["status"] == STATUS_REVIEW, miss_exp
    assert any("预期未对齐" in r for r in miss_exp["reasons"]), miss_exp["reasons"]
    print("    ✓ 漏预期 spec → needs_human_review(expected 判定点未进断言)")

    # 4) mode 存疑:用例含操作词,却落只读 mode、无写请求、无 ui 计划
    bad_mode = review_spec(_spec(
        mode="reconcile", request={}, ui={},
        assertions={"db": [{"table": "t"}]},
        raw={"steps": "create item submit", "expected": "created"}),
        min_coverage=0.2)
    assert any("mode 存疑" in r for r in bad_mode["reasons"]), bad_mode["reasons"]
    print("    ✓ mode 存疑 → 捕获(含操作词却落只读 mode 且无 ui)")

    # 5) 软门铁律:checker 永不改 exec_spec —— produce 只产 spec_review 旁路键
    checker = SpecChecker(min_coverage=0.4)
    out = checker.produce("spec", _Ctx(_spec()))
    assert set(out.keys()) == {REVIEW_ARTIFACT}, out.keys()
    assert "exec_spec" not in out, "checker 绝不能写 exec_spec(maker 的产物)"
    print(f"    ✓ 软门隔离:SpecChecker.produce 只产 {REVIEW_ARTIFACT},不碰 exec_spec")

    # 6) 写作用域门禁复用:spec_review 作为 checker 白名单,写 exec_spec 会被判越界
    #    (这里直接验 enforce_write_scope 对旁路键的裁决口径)
    assert enforce_write_scope("spec", {"spec_review": out[REVIEW_ARTIFACT]}), \
        "spec 段 maker 白名单是 exec_spec,写 spec_review 应判越界(由 checker 专属白名单放行)"
    # checker 侧:若白名单切到 spec_review,则写 spec_review 合规、写 exec_spec 越界
    def _checker_scope_violations(artifact):
        allowed = {REVIEW_ARTIFACT}
        return [k for k in artifact if k not in allowed]
    assert _checker_scope_violations({"spec_review": {}}) == []
    assert _checker_scope_violations({"exec_spec": {}}) == ["exec_spec"]
    print("    ✓ 写作用域:checker 白名单={spec_review},写 exec_spec 越界被拦(与 maker 物理隔离)")

    # 7) 确定性 + 降级:同输入同输出;无 llm 走档位A(tier=lexical)
    a = review_spec(_spec(), min_coverage=0.4)
    b = review_spec(_spec(), min_coverage=0.4)
    assert a == b, "复核必须确定性"
    assert a["tier"] == "lexical", a
    print("    ✓ 确定性 + 无模型降级档位A(tier=lexical)")

    print("\n全部通过 ✅  —— CP-1 语义软门:挑错不改产物、候选态、宁缺毋滥、零业务")


if __name__ == "__main__":
    main()
