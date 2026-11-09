"""CaseDisposition 一等公民 验证(离线、零环境):一条用例的 state/owner/need/evidence
装进同一个有类型对象,各消费者读它、不再各自用平行元组重推。中性夹具,毫秒级。
跑:python tests/test_disposition.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.disposition import CaseDisposition, classify_disposition, group_by_owner  # noqa: E402


def main():
    print("CaseDisposition 一等公民 验证:\n")

    # 1) PASS:无 owner/need,不计入待补,pending=False
    d_pass = classify_disposition("T1", "通过用例", "✅ PASS", "真实多源通过", "随便散文", verdict="PASS", refine=[])
    assert d_pass.owner == "" and d_pass.need == "" and d_pass.pending is False
    print("    ✓ PASS → owner/need 空、pending=False(不入待补清单)")

    # 2) FAIL:泛化映射判为 defect(已检出缺陷)
    d_fail = classify_disposition("T2", "失败用例", "🔶 FAIL", "跑了但不一致", "散文", verdict="FAIL", evidence="runs/r9", refine=[])
    assert d_fail.owner == "defect" and d_fail.pending is True and d_fail.evidence == "runs/r9"
    print(f"    ✓ FAIL → owner=defect、携带 evidence={d_fail.evidence}")

    # 3) 细化:tool(待建模)遇命中关键词的 refine 规则 → 锐化到 env(更具体归属)
    refine = [{"match": ["特定角色"], "owner": "env", "need": "需该角色账号"}]
    d_env = classify_disposition("T3", "角色受限", "🟡 PENDING·接口", "配端点即可",
                                 "本用例需特定角色操作", refine=refine)
    assert d_env.owner == "env" and d_env.need == "需该角色账号", (d_env.owner, d_env.need)
    # 同样 state、但散文不命中 → 保持泛化 tool
    d_tool = classify_disposition("T4", "普通接口", "🟡 PENDING·接口", "配端点即可", "无特殊要求", refine=refine)
    assert d_tool.owner == "tool", d_tool.owner
    print("    ✓ owner/need 由 envneeds 泛化映射+workspace 细化填(命中→env,未命中→tool)")

    # 4) group_by_owner:按 owner 聚合成 render_md 吃的 {owner:[(cid,name,need)]},已通过的剔除
    disps = [d_pass, d_fail, d_env, d_tool]
    groups = group_by_owner(disps)
    assert set(groups) == {"defect", "env", "tool"}, set(groups)          # 无 ""(PASS 不入)
    assert groups["env"] == [("T3", "角色受限", "需该角色账号")], groups["env"]
    assert all(isinstance(t, tuple) and len(t) == 3 for v in groups.values() for t in v)
    print(f"    ✓ group_by_owner 聚合正确且剔除已通过:{ {k: len(v) for k, v in groups.items()} }")

    # 5) 对象是一等公民:四个面都在它身上,可直接传递/读取,不依赖外部平行结构
    d = CaseDisposition(case_id="T5", name="n", verdict="PASS", state="✅ PASS",
                        why="w", owner="", need="", evidence="runs/x", blocked_by=["role"])
    assert d.blocked_by == ["role"] and d.evidence == "runs/x"
    print("    ✓ CaseDisposition 自带 {state, owner, need, evidence, blocked_by} 全部面")

    print("\n全部通过 ✅  —— 用例去向收敛为一个有类型对象,清单/环境需求/报告共读一份")


if __name__ == "__main__":
    main()
