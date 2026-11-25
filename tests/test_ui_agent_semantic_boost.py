"""planner 离线语义增强 + 候选留痕(全离线、零业务、不依赖模型)。

本轮真正的修复是**扩充通用 UI 同义词表**(core/ui_agent/semantic.py 的 ALIASES):
确定性的 equivalent 自会对同组同义词生效,用例"检索"能对上按钮"查询"、"明细"
对上"详情"——纯离线、无需任何 LLM。配套把每步候选打分落进决策,可复盘。

验证四件事:
  1. 扩词后同组同义措辞被 equivalent 判等价(100 分),选得中——补平"措辞刁钻
     选不中控件"的词法短板,且无需 LLM。
  2. 跨组词不误判为同义(不乱配)。
  3. explore 决策带候选打分(candidates),可复盘"为何选 A 不选 B"。
  4. 无同义命中、无 provider 时,行为确定(不乱点),与现状一致。

跑:python tests/test_ui_agent_semantic_boost.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.ui_agent.planner import ObservationPlanner, _score_control  # noqa: E402
from core.ui_agent.semantic import equivalent  # noqa: E402


def test_expanded_aliases_make_synonyms_equivalent() -> None:
    """扩词后同组同义词被判等价,跨组词不误判。"""
    assert equivalent("查询", "检索") is True        # 同属查询组
    assert equivalent("创建", "新建") is True        # 同属新建组
    assert equivalent("详情", "明细") is True        # 同属详情组
    assert equivalent("删除", "查询") is False       # 跨组,不误配
    assert equivalent("取消", "提交") is False       # 分属取消组/提交组
    print("  ✓ 扩词后 equivalent 同组真、跨组假,不误判")


def test_synonym_control_scores_full() -> None:
    """用例要"检索",控件叫"查询":equivalent 命中 → 满分 100,纯离线选得中。"""
    control = {"tag": "link", "text": "查询", "role": "link"}
    score = _score_control(control, "检索", "点击检索")
    assert score == 100.0, f"同义词应 equivalent 命中给 100,实得 {score}"
    print("  ✓ 同义措辞(检索↔查询)确定性满分,纯离线选得中")


def test_synonym_control_is_selected_offline() -> None:
    """端到端:指令"检索",页面只有"查询"控件,planner 应选中它并把动作目标
    改写为实际控件名"查询"(扩词前会漏;不改写则 runtime 拿"检索"点不中)。"""
    planner = ObservationPlanner("检索", [{"action": "click", "text": "检索"}])
    decision = planner.decide({"body_text": "", "controls": [
        {"tag": "link", "text": "查询", "role": "link"},
    ], "fields": []})
    assert decision.kind == "execute", f"同义目标可见应直接执行,实得 {decision.kind}"
    assert decision.action["text"] == "查询", \
        f"动作目标应改写为实际控件名'查询',实得 {decision.action.get('text')}"
    print("  ✓ 无模型下,'检索' 指令选中并改写为实际控件 '查询'")


def test_decision_carries_candidate_scores() -> None:
    """explore 决策应带候选打分明细,供复盘。"""
    planner = ObservationPlanner("检索", [{"action": "click", "text": "检索"}])
    decision = planner.decide({"body_text": "", "controls": [
        {"tag": "link", "text": "查询", "role": "link"},
        {"tag": "link", "text": "无关链接", "role": "link"},
    ], "fields": []})
    assert decision.candidates, "决策应带非空候选打分"
    top = decision.candidates[0]
    assert "name" in top and "score" in top
    assert top["name"] == "查询" and top["score"] == 100.0
    names = {item["name"] for item in decision.candidates}
    assert "无关链接" in names, "候选应覆盖全部可见控件(含低分项)以便复盘"
    print(f"  ✓ 决策留痕 {len(decision.candidates)} 个候选,top={top['name']}({top['score']})")


def test_no_synonym_no_provider_stays_blocked() -> None:
    """无同义命中、无 provider:行为确定(不乱点),与现状一致。"""
    planner = ObservationPlanner("检索数据", [{"action": "click", "text": "检索数据"}])
    decision = planner.decide({"body_text": "", "controls": [
        {"tag": "button", "text": "删除", "role": "button", "disabled": False},
    ], "fields": []})
    # "删除"既非同义也危险,不会被选;无 provider → 无安全路径 → blocked
    assert decision.kind == "blocked", f"无路径应 blocked,实得 {decision.kind}"
    print("  ✓ 无同义/无 provider 时确定性 blocked,不乱点")


def main() -> None:
    print("planner 离线语义增强 + 候选留痕\n")
    test_expanded_aliases_make_synonyms_equivalent()
    test_synonym_control_scores_full()
    test_synonym_control_is_selected_offline()
    test_decision_carries_candidate_scores()
    test_no_synonym_no_provider_stays_blocked()
    print("\n全部通过 ✅  —— 扩词纯离线补平措辞短板,决策可复盘,回退不变")


if __name__ == "__main__":
    main()
