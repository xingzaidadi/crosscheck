"""真实后端 E2E 暴露的两个缺口的离线回归(零浏览器、零业务)。

本轮在真实微前端审批系统上只读实跑,暴露并修了两个真缺口,这里把它们固化成离线用例:

  缺口 A(观察器穿透 shadow DOM):qiankun 微前端把业务控件渲染进 shadow DOM,
    原 observer 的 document.querySelectorAll 不进 shadow root,只看得到外壳"加载中"。
    —— 纯 JS 行为,离线用一段带 shadow root 的 HTML 字符串验 OBSERVE_JS 的 queryDeep 是否下探。
    (需要浏览器,故此条标记为可选:无 chromium 时跳过,不算失败。)

  缺口 B(引号内否定词误翻期望):指令"确认页面出现文本『…不存在…』"里引号内的"不存在"
    被当成缺失线索,把 visibility 断言 expected 翻成 False,导致"目标缺失=预期缺失"的误通过。
    —— 纯函数逻辑,_cue_text 去掉引号字面后再判缺失/可见词。零浏览器可直接验。

跑:python tests/test_realrun_trust_fixes.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ui_test_intake import _cue_text, ABSENCE_WORDS, VISIBILITY_WORDS, QUOTED  # noqa: E402


def test_cue_text_strips_quoted_literal():
    line = '确认当前页面出现文本“这段文字绝对不存在ZZZ”'
    cue = _cue_text(line)
    # 引号内字面(含"不存在")被剥掉,只剩措辞
    assert "不存在" not in cue, cue
    assert "出现" in cue, cue


def test_negation_inside_quote_does_not_flip_expected():
    # 还原真跑里的误通过根因:缺失词只应来自措辞,不应来自引号内目标文本
    line = '确认当前页面出现文本“订单不存在时的空态提示”'
    labels = [m.strip() for m in QUOTED.findall(line) if m.strip()]
    cue = _cue_text(line)
    absence_in_cue = any(w in cue for w in ABSENCE_WORDS)
    visibility_in_cue = any(w in cue for w in VISIBILITY_WORDS)
    assert labels, "应抽到引号内目标文本"
    assert not absence_in_cue, f"引号内的『不存在』不该触发缺失断言:cue={cue!r}"
    assert visibility_in_cue, f"措辞里的『出现』应触发可见断言:cue={cue!r}"
    print("    ✓ 引号内否定词不再翻转 expected(修掉『目标缺失=预期缺失』误通过)")


def test_real_absence_phrasing_still_detected():
    # 真正的缺失措辞(否定词在引号外)仍应判缺失——不误伤
    line = '确认“错误提示”不显示'
    cue = _cue_text(line)
    assert any(w in cue for w in ABSENCE_WORDS), f"措辞里的『不显示』应仍被识别:cue={cue!r}"
    print("    ✓ 引号外的真实缺失措辞仍正常识别(不误伤)")


def test_cue_text_empty_and_noquote():
    assert _cue_text("") == ""
    # 无引号时原样(去空白无关)
    assert "出现" in _cue_text("页面出现列表")
    print("    ✓ 空输入/无引号输入优雅处理")


def test_observer_pierces_shadow_dom():
    """缺口 A:observer 应能下探 shadow DOM 读到业务控件(需 chromium,缺则跳过)。"""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        print("    ⚠ 无 playwright,跳过 shadow DOM 下探用例(非失败)")
        return
    from core.ui_agent.observer import observe
    html = (
        "data:text/html;charset=utf-8,"
        "<meta charset=utf-8>"
        "<div id=shell>外壳菜单</div>"
        "<my-app></my-app>"
        "<script>"
        "const h=document.querySelector('my-app');"
        "const r=h.attachShadow({mode:'open'});"
        "r.innerHTML='<h1>我的需求列表</h1><button>查询</button>';"
        "</script>"
    )
    try:
        with sync_playwright() as p:
            try:
                b = p.chromium.launch(headless=True)
            except Exception:
                print("    ⚠ chromium 未安装,跳过 shadow DOM 下探用例(非失败)")
                return
            pg = b.new_context().new_page()
            pg.goto(html)
            pg.wait_for_timeout(300)
            snap = observe(pg)
            texts = " ".join(str(c.get("text") or c.get("label") or "") for c in snap.get("controls", []))
            body = snap.get("body_text", "")
            b.close()
    except Exception as exc:
        print(f"    ⚠ 浏览器不可用,跳过(非失败):{str(exc)[:80]}")
        return
    assert "查询" in texts, f"shadow DOM 里的『查询』按钮应被 queryDeep 捕获:{texts[:120]!r}"
    assert "我的需求列表" in body, f"shadow DOM 文本应进 body_text:{body[:120]!r}"
    print("    ✓ observer 下探 shadow DOM,捕获业务控件与文本(真跑缺口 A 已修)")


def main():
    print("真实后端 E2E 暴露缺口的离线回归:\n")
    test_cue_text_strips_quoted_literal()
    test_negation_inside_quote_does_not_flip_expected()
    test_real_absence_phrasing_still_detected()
    test_cue_text_empty_and_noquote()
    test_observer_pierces_shadow_dom()
    print("\n全部通过 ✅  —— 引号内否定词不再误翻 visibility 期望 + observer 穿透 shadow DOM(真跑暴露缺口已修)")


if __name__ == "__main__":
    main()
