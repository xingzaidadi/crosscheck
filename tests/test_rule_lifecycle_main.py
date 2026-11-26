"""core.rule_lifecycle + core.review_rules.parse_review_md 真执行回归(main()+assert)。

rule_lifecycle 对挖掘出的规则候选做去重提案(propose_rules)与冗余/未命中剪枝建议
(prune_rules),全程"只建议不写 REVIEW.md"守人审铁律。此前覆盖仅 11%。本文件连带
覆盖 parse_review_md 解析,在 run_tests.py 下真执行。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.rule_lifecycle import propose_rules, prune_rules, _rule_to_md
from core.review_rules import parse_review_md


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


REVIEW = """# REVIEW
## RULE: 下单库存校验
- trigger: order, inventory
- check: 下单后库存必须扣减且不为负
- incident: INC-2024-001 超卖事故

## RULE: 冗余规则甲
- trigger: order
- check: 共享检查X
- incident: 短

## RULE: 冗余规则乙
- trigger: pay
- check: 共享检查X
- incident: 更完整的事故描述用于择优保留
"""


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    # 1) parse_review_md 解析三条规则,字段齐。
    rules = parse_review_md(REVIEW)
    _assert(len(rules) == 3, f"应解析 3 条规则, got {len(rules)}")
    first = rules[0]
    _assert(first["name"] == "下单库存校验", "规则名")
    _assert(first["triggers"] == ["order", "inventory"], "triggers 逗号拆分")
    _assert(first["check"] == "下单后库存必须扣减且不为负", "check 字段")
    _assert(first["incident"].startswith("INC-2024-001"), "incident 字段")
    print("[1] parse_review_md 解析 ✓")

    # 2) _rule_to_md 渲染;空 triggers 给占位。
    md = _rule_to_md({"name": "R", "triggers": [], "check": "c", "incident": "i"})
    _assert("## RULE: R" in md, "渲染标题")
    _assert("TODO_填写改动域" in md, "空 triggers 占位")
    print("[2] _rule_to_md 渲染 ✓")

    # 3) propose_rules:check 已存在的判重复,新的进 new_candidates。
    candidates = [
        {"name": "新规则", "check": "全新检查Y", "incident": "i1", "triggers": ["x"]},
        {"name": "重复", "check": "下单后库存必须扣减且不为负", "incident": "i2"},  # 已存在
    ]
    prop = propose_rules(candidates, REVIEW)
    _assert(len(prop["new_candidates"]) == 1, "1 条新候选")
    _assert(prop["new_candidates"][0]["name"] == "新规则", "新候选是全新检查")
    _assert(len(prop["duplicates"]) == 1, "1 条重复")
    _assert(prop["duplicates"][0]["name"] == "重复", "重复判定")
    _assert("## RULE: 新规则" in prop["review_md_snippet"], "snippet 只含新候选")
    _assert("## RULE: 重复" not in prop["review_md_snippet"], "snippet 不含重复")
    print("[3] propose_rules 去重提案 ✓")

    # 4) prune_rules:共享 check 的两条,保留 incident 更完整者,另一条建议剪。
    pr = prune_rules(REVIEW)
    pruned_names = {r["name"] for r in pr["prune"]}
    kept_names = {r["name"] for r in pr["keep"]}
    _assert("冗余规则甲" in pruned_names, "incident 短的被剪")
    _assert("冗余规则乙" in kept_names, "incident 完整的保留")
    _assert("下单库存校验" in kept_names, "唯一 check 的规则保留")
    for r in pr["prune"]:
        if r["name"] == "冗余规则甲":
            _assert(r["prune_reason"] == "duplicate_check", "剪枝理由=duplicate_check")
    print("[4] prune_rules 冗余择优保留 ✓")

    # 5) prune_rules 带 usage:从未命中的规则建议剪(never_matched)。
    pr2 = prune_rules(REVIEW, usage={"下单库存校验": 0})
    reasons = {r["name"]: r.get("prune_reason") for r in pr2["prune"]}
    _assert(reasons.get("下单库存校验") == "never_matched", "usage=0 → never_matched")
    print("[5] prune_rules never_matched ✓")

    # 6) 不写盘铁律:两函数都只返回建议,不碰 REVIEW.md(返回结构里无写路径副作用)。
    _assert(set(prop.keys()) == {"new_candidates", "duplicates", "review_md_snippet"}, "propose 只返回建议")
    _assert(set(pr.keys()) == {"keep", "prune"}, "prune 只返回建议")
    print("[6] 只建议不写盘 ✓")

    print("\nALL PASS · core.rule_lifecycle + parse_review_md(解析/渲染/去重提案/冗余剪枝/未命中)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
