"""插件注册表收口 验证(离线、零环境):通用 kind→key→impl 注册表 +
三类活分发(case_reader / login_mode / adapter)确已收口到 registry。
跑:python tests/test_registry.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import registry  # noqa: E402


def main():
    print("插件注册表收口 验证:\n")

    # 1) 基本语义:register / get / resolve / keys + 装饰器形态
    registry.register("demo", "a", 1)

    @registry.register("demo", "b")
    def _b():
        return 2
    assert registry.get("demo", "a") == 1
    assert registry.get("demo", "missing", "DFT") == "DFT"
    assert registry.resolve("demo", "b") is _b
    assert registry.keys("demo") == ["a", "b"], registry.keys("demo")
    try:
        registry.resolve("demo", "nope")
        raise AssertionError("resolve 未注册项应抛 KeyError")
    except KeyError as e:
        assert "nope" in str(e) and "demo" in str(e)
    print("    ✓ register/get(默认兜底)/resolve(缺失抛错并列已注册)/keys/装饰器 全部正确")

    # 2) case_reader 收口:导入 case_source 即把扩展名读取器登记进 registry
    import core.case_source  # noqa: F401
    for ext in (".xlsx", ".xlsm", ".xltx", ".csv", ".json"):
        assert registry.get("case_reader", ext) is not None, ext
    print(f"    ✓ case_reader 已登记:{registry.keys('case_reader')}")

    # 2b) read_cases 走 registry:临时注册一个 .fake 读取器,read_cases 即认(零改框架码可扩格式)
    from core.case_source import RawCase, read_cases
    registry.register("case_reader", ".fake", lambda path, sheet=None: [RawCase(name="FROM_FAKE", row=1)])
    rows = read_cases("x.fake")
    assert len(rows) == 1 and rows[0].name == "FROM_FAKE", rows
    print("    ✓ read_cases 按 registry 分发:新注册的 .fake 读取器被即时采用,未碰框架码")

    # 3) login_mode 收口:导入 login 即登记 manual/credential,统一 (profile,creds,session_file) 签名
    import core.login  # noqa: F401
    assert set(registry.keys("login_mode")) == {"manual", "credential"}, registry.keys("login_mode")
    called = {}
    registry.register("login_mode", "manual",
                      lambda profile, creds, session_file: called.update(ok=(profile, creds, session_file)))
    registry.resolve("login_mode", "manual")("P", "C", "S")
    assert called["ok"] == ("P", "C", "S")
    print(f"    ✓ login_mode 已收口(if-elif 链→注册表):{registry.keys('login_mode')}")

    # 4) adapter 收口:connectors 登记 api/ui 工厂;make_adapter 按 kind 造,未知 kind 抛错
    from core.connectors import make_adapter
    assert set(registry.keys("adapter")) >= {"api", "ui"}, registry.keys("adapter")
    registry.register("adapter", "fake", lambda **kw: ("FAKE_ADAPTER", kw))
    got = make_adapter("fake", x=9)
    assert got == ("FAKE_ADAPTER", {"x": 9}), got
    try:
        make_adapter("no_such_kind")
        raise AssertionError("make_adapter 未知 kind 应抛 KeyError")
    except KeyError:
        pass
    print(f"    ✓ adapter 已收口(写死 ApiAdapter 构造→工厂):{registry.keys('adapter')}")

    print("\n全部通过 ✅  —— 四类插件收口到一处:一处注册、一处查找,接入新实现零改框架码")


if __name__ == "__main__":
    main()
