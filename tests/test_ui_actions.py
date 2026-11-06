"""
语义 UI 动作回放 验证(本地 mock 页面 + Playwright,离线)。

证明复杂控件能按语义定位回放(之前超时的那几类):
  文本、原生下拉、级联(逐级点选)、可编辑网格单元格(按表头文本定位列)、日期。
mock 页面与任何业务无关 —— 证明回放器是通用的。

跑:python tests/test_ui_actions.py(需本地已装 Playwright 浏览器)
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
<div class="form-item"><span class="label">字段描述</span><input id="desc"></div>
<div class="form-item"><span class="label">币种</span>
  <select id="cur"><option>请选择</option><option>人民币</option><option>美元</option></select></div>
<div class="form-item" id="fi-cat"><span class="label">多级类目</span><span class="trigger">请选择</span></div>
<div class="panel" id="catPanel" style="display:none">
  <div class="opt">一级</div><div class="opt">二级</div><div class="opt">三级</div></div>
<div id="catResult"></div>
<table><thead><tr><th>数量</th><th>单价</th></tr></thead>
  <tbody><tr><td><input id="qty"></td><td><input id="price"></td></tr></tbody></table>
<div class="form-item"><span class="label">交付日期</span><input id="dt"></div>
<script>
  document.getElementById('fi-cat').onclick=function(){document.getElementById('catPanel').style.display='block';};
  document.querySelectorAll('#catPanel .opt').forEach(function(o){
    o.onclick=function(){document.getElementById('catResult').innerText += o.innerText + ',';};});
</script></body></html>"""


def main():
    d = tempfile.mkdtemp()
    page_path = os.path.join(d, "form.html").replace("\\", "/")
    open(page_path, "w", encoding="utf-8").write(HTML)

    from playwright.sync_api import sync_playwright
    actions = [
        {"action": "text", "label": "字段描述", "value": "AUTOTEST desc"},
        {"action": "select", "label": "币种", "value": "美元"},
        {"action": "cascader", "label": "多级类目", "path": ["一级", "二级", "三级"]},
        {"action": "grid_cell", "column": "单价", "value": "25", "row": 0},
        {"action": "date", "label": "交付日期", "value": "2026-11-20"},
    ]
    print("语义 UI 动作回放 验证:\n")
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_context().new_page()
        pg.goto(f"file://{page_path}")
        results = replay(pg, actions)
        bad = [r for r in results if not r["ok"]]
        assert not bad, bad
        print("    ✓ 5 类控件回放全部成功:" + " / ".join(r["target"] for r in results))

        assert pg.locator("#desc").input_value() == "AUTOTEST desc"
        assert pg.locator("#cur").input_value() == "美元"
        assert pg.locator("#price").input_value() == "25"
        assert pg.locator("#dt").input_value() == "2026-11-20"
        cat = pg.locator("#catResult").inner_text()
        assert cat == "一级,二级,三级,", repr(cat)
        b.close()
    print("    ✓ DOM 落值正确:文本/原生下拉/网格单元格/日期 + 级联逐级选中(一级→二级→三级)")
    print("\n全部通过 ✅  —— 通用语义 UI 回放(含级联/网格/日期复杂控件)就位")


if __name__ == "__main__":
    main()
