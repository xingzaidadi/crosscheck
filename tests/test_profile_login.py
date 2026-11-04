"""
Site Profile 加载 + 声明式登录步骤(B 模式)的单元验证 —— 不开浏览器。

验证通用化的两个关键点:
  - 中性夹具 profile(tests/fixtures/workspace/profiles/demo.yaml)能被正确解析;
  - login._run_steps 能把 value_from 从凭据里解析进 fill,缺字段时明确报错。

跑:python tests/test_profile_login.py
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.workspace import set_workspace  # noqa: E402
from core.profile import load_profile, list_profiles  # noqa: E402
from core.login import _run_steps, LoginError  # noqa: E402

FIXTURE_WS = Path(__file__).resolve().parent / "fixtures" / "workspace"


def test_load_demo_profile():
    prof = load_profile("demo")
    assert prof.site == "demo"
    assert prof.base_url.startswith("https://")
    assert prof.login.mode == "manual"
    assert prof.db_readonly == "demo_db"
    assert prof.defaults["table"] == "items"
    # 登录态按站点隔离
    assert prof.session_file.endswith("demo.json")
    print("    ✓ demo profile 解析正确(站点身份已从代码解耦)")


def test_list_profiles_hides_template():
    names = list_profiles()
    assert "demo" in names
    assert "_example" not in names  # 下划线开头的模板不列出
    print(f"    ✓ list_profiles={names},模板 _example 已隐藏")


def test_credential_steps_resolve():
    steps = [
        {"fill": {"selector": "#email", "value_from": "username"}},
        {"fill": {"selector": "#pwd", "value_from": "password"}},
        {"click": {"selector": "button.login"}},
    ]
    page = FakePage()
    _run_steps(page, steps, {"username": "autotest_a", "password": "s3cret"})
    assert ("fill", "#email", "autotest_a") in page.calls
    assert ("fill", "#pwd", "s3cret") in page.calls
    assert ("click", "button.login") in page.calls
    print("    ✓ B 模式 value_from 从凭据解析进填表,顺序执行")


def test_missing_credential_errors():
    steps = [{"fill": {"selector": "#pwd", "value_from": "password"}}]
    try:
        _run_steps(FakePage(), steps, {"username": "only_user"})  # 缺 password
        raise AssertionError("缺凭据本应报 LoginError")
    except LoginError as e:
        assert "password" in str(e)
    print("    ✓ 缺凭据字段时明确报 LoginError(不静默填空)")


class FakePage:
    """只记录调用,不碰网络。用来验证登录步骤的解析逻辑。"""
    def __init__(self):
        self.calls: list[tuple] = []

    def goto(self, url, **k): self.calls.append(("goto", url))
    def fill(self, sel, val): self.calls.append(("fill", sel, val))
    def click(self, sel, **k): self.calls.append(("click", sel))
    def press(self, sel, key): self.calls.append(("press", sel, key))
    def wait_for_selector(self, sel, **k): self.calls.append(("wait_for", sel))
    def wait_for_timeout(self, ms): self.calls.append(("wait_ms", ms))


def main():
    set_workspace(FIXTURE_WS)
    print("Site Profile + 登录模块验证:\n")
    for fn in (test_load_demo_profile, test_list_profiles_hides_template,
               test_credential_steps_resolve, test_missing_credential_errors):
        fn()
    print("\n全部通过 ✅  —— 换站点=新写一个 profile,内核不改;A/B 登录逻辑就位")


if __name__ == "__main__":
    main()
