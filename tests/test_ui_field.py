"""
UI 字段联动/只读断言 验证(本地 mock + Playwright,离线)。
验三种承载:禁用 input(联动带出+锁定)、普通 input(可编辑)、纯文本(只读展示);含反例。

跑:python tests/test_ui_field.py
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

from core.ui_field import check_fields  # noqa: E402

HTML = """<!doctype html><html><head><meta charset=utf-8></head><body>
<div class="form-item"><span class="label">采购品类</span><input value="三级" disabled></div>
<div class="form-item"><span class="label">数量</span><input value="2"></div>
<div class="form-item"><span class="label">需求部门</span><span>研发部</span></div>
</body></html>"""


def main():
    d = tempfile.mkdtemp()
    pp = os.path.join(d, "f.html").replace("\\", "/")
    open(pp, "w", encoding="utf-8").write(HTML)
    print("UI 字段联动/只读断言 验证:\n")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_context().new_page()
        pg.goto(f"file://{pp}")

        ok, layer = check_fields(pg, [
            {"label": "采购品类", "equals": "三级", "readonly": True},   # 联动带出+锁定
            {"label": "数量", "equals": "2", "readonly": False},         # 可编辑
            {"label": "需求部门", "equals": "研发部", "readonly": True},  # 只读展示(纯文本)
        ])
        assert ok, layer["rows"]
        print("    ✓ 正例:带出值+只读态 三种承载全对(禁用input/可编辑input/纯文本展示)")

        bad1, _ = check_fields(pg, [{"label": "数量", "readonly": True}])   # 其实可编辑
        assert not bad1, "可编辑字段断言只读应失败"
        bad2, _ = check_fields(pg, [{"label": "采购品类", "equals": "二级"}])  # 实际三级
        assert not bad2, "值不符应失败"
        bad3, _ = check_fields(pg, [{"label": "不存在字段", "equals": "x"}])
        assert not bad3, "字段找不到应失败"
        print("    ✓ 反例:只读态错 / 值错 / 字段缺 都如实判失败")
        b.close()
    print("\n全部通过 ✅  —— UI 字段联动/只读断言就位(解锁字段联动/只读类用例)")


if __name__ == "__main__":
    main()
