"""
UI 录制蒸馏 验证(离线):
  1) 纯函数 events_to_page_model:原始交互事件 → 语义 page_model(去重/日期识别/点选/忽略长文本)。
  2) 录制→回放 round-trip:事件蒸馏出的 page_model 交给 ui_actions.replay 跑本地 mock 页,DOM 落值正确。
证明"录一次 → 自动生成步骤 → 回放"闭环(带标签控件);复杂控件(级联需先展开/网格无标签)留作已知边界。

跑:python tests/test_ui_record.py
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

from core.ui_record import events_to_page_model  # noqa: E402
from core.ui_actions import replay  # noqa: E402

HTML = """<!doctype html><html><head><meta charset=utf-8></head><body>
<div class="form-item"><span class="label">字段描述</span><input id="desc"></div>
<div class="form-item"><span class="label">币种</span>
  <select id="cur"><option>请选择</option><option>人民币</option><option>美元</option></select></div>
<div class="form-item"><span class="label">交付日期</span><input id="dt"></div>
</body></html>"""


def main():
    print("UI 录制蒸馏 验证:\n")

    # 1) 纯函数:事件 → page_model
    events = [
        {"kind": "input", "tag": "input", "type": "text", "label": "字段描述", "value": "he"},
        {"kind": "input", "tag": "input", "type": "text", "label": "字段描述", "value": "hello"},   # 去重取最后
        {"kind": "change", "tag": "select", "label": "币种", "value": "美元"},
        {"kind": "click", "tag": "div", "label": "多级类目", "text": "一级"},
        {"kind": "click", "tag": "div", "label": "多级类目", "text": "一级"},                        # 连点去重
        {"kind": "click", "tag": "div", "label": "多级类目", "text": "二级"},
        {"kind": "click", "tag": "div", "label": "", "text": "这是一段很长的说明文本不应被当成点选步骤因为超过长度上限"},  # 忽略
        {"kind": "input", "tag": "input", "type": "date", "label": "交付日期", "value": "2026-11-20"},
    ]
    model = events_to_page_model(events)
    assert model == [
        {"action": "text", "label": "字段描述", "value": "hello"},
        {"action": "select", "label": "币种", "value": "美元"},
        {"action": "click", "text": "一级"},
        {"action": "click", "text": "二级"},
        {"action": "date", "label": "交付日期", "value": "2026-11-20"},
    ], model
    print("    ✓ 事件→page_model: 文本去重、下拉、点选(连点去重+忽略长文本)、日期识别 正确")

    # 2) round-trip:蒸馏出的带标签步骤交给 replay 跑 mock 页
    d = tempfile.mkdtemp()
    pp = os.path.join(d, "f.html").replace("\\", "/")
    open(pp, "w", encoding="utf-8").write(HTML)
    labeled = [s for s in model if s.get("action") in ("text", "select", "date")]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_context().new_page()
        pg.goto(f"file://{pp}")
        res = replay(pg, labeled)
        assert all(r["ok"] for r in res), res
        assert pg.locator("#desc").input_value() == "hello"
        assert pg.locator("#cur").input_value() == "美元"
        assert pg.locator("#dt").input_value() == "2026-11-20"
        b.close()
    print("    ✓ round-trip: 录制蒸馏的步骤回放到页面,DOM 落值正确(录一次→自动步骤→回放)")
    print("\n全部通过 ✅  —— UI 录制→蒸馏→回放 闭环(带标签控件)就位")


if __name__ == "__main__":
    main()
