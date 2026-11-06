"""
前端校验报错断言 验证(离线、零业务)。
很多"非法值拦截"是前端校验(后端不复查),只能走 UI 读页面校验提示。

跑:python tests/test_ui_validation.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ui_validation import check_validation  # noqa: E402


def main():
    print("前端校验报错断言 验证:\n")
    errors = ["请输入大于0的数量", "交付日期不能早于今天"]

    ok, layer = check_validation(errors, ["大于0", "不能早于今天"])
    assert ok, layer["rows"]
    print("    ✓ 预期提示子串都在页面报错里 → 通过")

    bad, _ = check_validation(errors, ["行号重复"])
    assert not bad, "页面没这条报错应失败"
    bad2, _ = check_validation([], ["任意"])
    assert not bad2, "页面无任何报错应失败"
    print("    ✓ 缺失提示 / 页面无报错 → 如实判失败")
    print("\n全部通过 ✅  —— 前端校验报错断言就位(前端校验类走 UI 测)")


if __name__ == "__main__":
    main()
