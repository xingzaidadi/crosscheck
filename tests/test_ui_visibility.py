"""core/ui_visibility.py 离线测试:本地起静态页,验命名控件 present/absent 判定,零业务中性域。
跑:python tests/test_ui_visibility.py(需本地 Playwright)
"""
import sys
from pathlib import Path
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.ui_visibility import check_visibility

# 中性页面:一个可见按钮"保存"、一个隐藏按钮"删除"(display:none)、无"归档"按钮。
HTML = """<!doctype html><html><head><meta charset=utf-8></head><body>
<button id="save">保存</button>
<button id="del" style="display:none">删除</button>
<a href="#" class="edit-link">编辑</a>
</body></html>"""


def main():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_context().new_page()
        page.set_content(HTML)

        # 1) 可见按钮 present=True → 通过
        ok, layer = check_visibility(page, [{"label": "保存", "present": True}])
        assert ok, layer
        print("    ✓ 可见控件 present=True 判通过")

        # 2) 隐藏按钮 present=False → 通过(期望不可见,实际隐藏)
        ok, _ = check_visibility(page, [{"label": "删除", "present": False}])
        assert ok, "隐藏控件 present=False 应通过"
        print("    ✓ 隐藏控件 present=False 判通过")

        # 3) 隐藏按钮 present=True → 失败(期望可见,实际隐藏)
        ok, _ = check_visibility(page, [{"label": "删除", "present": True}])
        assert not ok, "隐藏控件 present=True 应失败"
        print("    ✓ 隐藏控件 present=True 如实判失败")

        # 4) 不存在控件 present=False → 通过
        ok, _ = check_visibility(page, [{"label": "归档", "present": False}])
        assert ok, "不存在控件 present=False 应通过"
        print("    ✓ 不存在控件 present=False 判通过")

        # 5) 不存在控件 present=True → 失败
        ok, _ = check_visibility(page, [{"label": "归档", "present": True}])
        assert not ok, "不存在控件 present=True 应失败"
        print("    ✓ 不存在控件 present=True 如实判失败")

        # 6) selector 定位
        ok, _ = check_visibility(page, [{"selector": "a.edit-link", "present": True}])
        assert ok, "selector 命中可见元素应通过"
        print("    ✓ selector 定位可见元素判通过")

        # 7) 多项混合:全对 → 通过
        ok, layer = check_visibility(page, [
            {"label": "保存", "present": True},
            {"label": "删除", "present": False},
            {"label": "归档", "present": False},
        ])
        assert ok, layer
        print("    ✓ 多项混合全对判通过")

        b.close()
    print("\nUI 元素可见性断言 通过 ✅  —— 解锁按钮显示/隐藏类用例")


if __name__ == "__main__":
    main()
