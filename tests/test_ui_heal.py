"""
选择器自愈 验证(本地 mock 页面 + Playwright,离线)。

同一组字段用 5 种不同结构承载;证明主策略(form-item)不成立时,按备用策略也能定位,
并报告"用了哪条策略"(= 发生自愈,供回写知识待审)。结构与业务无关 —— 通用。

跑:python tests/test_ui_heal.py
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

HTML = """<!doctype html><html><head><meta charset=utf-8></head><body>
<div class="form-item"><span class="label">字段A</span><input id="a"></div>
<div><label for="b">字段B</label><input id="b"></div>
<div><label>字段C</label><input id="c"></div>
<input id="d" placeholder="字段D">
<input id="e" aria-label="字段E">
</body></html>"""


def main():
    d = tempfile.mkdtemp()
    pp = os.path.join(d, "f.html").replace("\\", "/")
    open(pp, "w", encoding="utf-8").write(HTML)

    actions = [{"action": "text", "label": f"字段{x}", "value": f"V{x}"} for x in "ABCDE"]
    print("选择器自愈 验证:\n")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_context().new_page()
        pg.goto(f"file://{pp}")
        res = replay(pg, actions)
        assert all(r["ok"] for r in res), res
        for cid in "abcde":
            assert pg.locator(f"#{cid}").input_value() == f"V{cid.upper()}", cid
        b.close()

    heals = {r["target"]: r.get("heal", "form-item") for r in res}
    assert heals["字段A"] == "form-item", heals
    assert heals["字段B"] == "label-for", heals
    assert heals["字段C"] == "label-sibling", heals
    assert heals["字段D"] == "placeholder", heals
    assert heals["字段E"] == "aria-label", heals
    print("    ✓ 5 种结构全部定位成功,DOM 落值正确")
    print(f"    ✓ 自愈策略如实上报: {heals}")
    print("\n全部通过 ✅  —— 选择器自愈(主策略失效按备用策略找回控件并记账)就位")


if __name__ == "__main__":
    main()
