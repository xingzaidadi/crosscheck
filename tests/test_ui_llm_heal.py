"""
LLM 选择器重解析兜底 验证(本地 mock + Playwright,离线)。

控件没有 form-item/label/placeholder/aria 任何确定性线索,只有一段无关联的说明文字;
确定性策略全失败 → 注入的 llm_resolver 看候选控件选中它(strat=llm);不注入则定位失败。
llm_resolver 由 skill 的会话 LLM 充当,这里用假 resolver 验证机制(执行期默认不启用、仍确定性)。

跑:python tests/test_ui_llm_heal.py
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

from core.ui_actions import replay  # noqa: E402

# weird 控件无任何标准线索;某字段只是页面上一段游离文字
HTML = """<!doctype html><html><head><meta charset=utf-8></head><body>
<div>某字段(说明文字,和输入框没有 label/for/placeholder 关联)</div>
<input id="weird">
</body></html>"""


def main():
    d = tempfile.mkdtemp()
    pp = os.path.join(d, "f.html").replace("\\", "/")
    open(pp, "w", encoding="utf-8").write(HTML)
    actions = [{"action": "text", "label": "某字段", "value": "V"}]

    print("LLM 选择器重解析兜底 验证:\n")
    from playwright.sync_api import sync_playwright

    seen = {}
    def fake_llm(label, candidates):
        seen["label"] = label
        seen["n"] = len(candidates)
        # 真实场景由会话 LLM 读 candidates(含附近文字)判断;这里直接选中 weird
        return "#weird"

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_context().new_page()
        pg.goto(f"file://{pp}")

        # 不给 llm_resolver:确定性全失败 → 定位不到
        r0 = replay(pg, actions)
        assert not r0[0]["ok"], "无 LLM 兜底时不该定位到"
        print("    ✓ 无 LLM 兜底:确定性策略全失败,如实报失败")

        # 给 llm_resolver:兜底命中
        r1 = replay(pg, actions, llm_resolver=fake_llm)
        assert r1[0]["ok"] and r1[0].get("heal") == "llm", r1
        assert pg.locator("#weird").input_value() == "V"
        assert seen.get("label") == "某字段" and seen.get("n", 0) >= 1
        b.close()
    print(f"    ✓ 注入 LLM 兜底:收到候选 {seen['n']} 个 → 选中控件,strat=llm,DOM 落值正确")
    print("\n全部通过 ✅  —— LLM 选择器重解析兜底就位(默认不启用,执行期仍确定性)")


if __name__ == "__main__":
    main()
