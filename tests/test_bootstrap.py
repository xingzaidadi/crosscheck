"""极简自举 验证(离线、零业务):注入假探测/登录,验 URL 解析、UI 套件识别、profile 生成。
跑:python tests/test_bootstrap.py
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

from core.workspace import set_workspace  # noqa: E402
from core.bootstrap import derive_site_and_base, detect_ui_kit, bootstrap  # noqa: E402
from core.profile import load_profile  # noqa: E402


def main():
    print("极简自举 验证:\n")

    site, base = derive_site_and_base("https://shop.test.example.cn/purchase/new?x=1")
    assert site == "shop" and base == "https://shop.test.example.cn", (site, base)
    print(f"    ✓ URL 解析: site={site} base={base}")

    # UI 套件识别:一堆组件类 + 一些工具类噪声
    classes = ["hi-v5-form-item foo", "hi-v5-picker", "hi-v5-button", "flex items-center",
               "hi-v5-table-body", "text-sm", "min-w-0"]
    kit = detect_ui_kit(classes)
    assert kit["kit"] == "hi" and kit["confidence"] > 0.5, kit
    print(f"    ✓ UI 套件识别: kit={kit['kit']} conf={kit['confidence']} (滤掉 flex/text/min)")

    assert detect_ui_kit(["flex", "text-sm"])["kit"] == "generic"
    assert detect_ui_kit(["ant-form-item", "ant-btn", "ant-input"])["kit"] == "ant"
    print("    ✓ 纯工具类→generic;antd→ant")

    # 端到端自举(注入假探测/登录)→ 写 profile + accounts,且可被 load_profile 读回
    set_workspace(tempfile.mkdtemp())
    def fake_detect(url):
        return "https://shop.test.example.cn/home", ["hi-v5-form-item", "hi-v5-picker", "hi-v5-btn"]
    logins = {}
    def fake_login(site, role):
        p = f"/auth/{site}__{role}.json"; logins[role] = p; return p
    res = bootstrap("https://shop.test.example.cn/purchase/new",
                    roles=["demander", "acceptor"], detect_fn=fake_detect, login_fn=fake_login,
                    db_readonly="shop_db")
    assert res["site"] == "shop" and res["ui_kit"]["kit"] == "hi", res
    assert set(res["roles"]) == {"demander", "acceptor"}, res
    print(f"    ✓ 自举完成: {res['profile_path']}")

    prof = load_profile("shop")
    assert prof.base_url == "https://shop.test.example.cn"
    assert prof.login.mode == "manual"
    assert prof.defaults.get("ui_kit") == "hi"
    assert prof.db_readonly == "shop_db"
    print("    ✓ 生成的 profile 可被 load_profile 读回,字段正确")

    print("\n全部通过 ✅  —— 一个 URL + 登录,自动生成 profile,用户不写 yaml,零业务离线可测")


if __name__ == "__main__":
    main()
