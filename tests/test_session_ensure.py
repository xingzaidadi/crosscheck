"""
登录态自动续期 —— 选择逻辑 验证(纯函数,离线、零业务)。
挑"该续哪些会话":只续 B 模式(credential)且被本批引用的站点。
真实续期(ensure_session 检活+重登)是活链路,这里只测选择逻辑。

跑:python tests/test_session_ensure.py
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.session_ensure import referenced_sessions, should_ensure  # noqa: E402


def main():
    print("登录态自动续期(选择逻辑)验证:\n")

    specs = [
        SimpleNamespace(session="ws/.auth/siteA.json", approve={}),
        SimpleNamespace(session="ws/.auth/siteB.json",
                        approve={"session": "ws/.auth/bpm.json"}),
        SimpleNamespace(session="", approve=None),
    ]
    ref = referenced_sessions(specs)
    assert ref == {"siteA.json", "siteB.json", "bpm.json"}, ref
    print(f"    ✓ 收集本批引用的会话(主动作+审批): {sorted(ref)}")

    # 只续 credential 且被引用的
    assert should_ensure("credential", "x/.auth/siteA.json", ref) is True
    assert should_ensure("credential", "x/.auth/bpm.json", ref) is True
    assert should_ensure("manual", "x/.auth/siteA.json", ref) is False, "A 模式不自动续"
    assert should_ensure("credential", "x/.auth/other.json", ref) is False, "没被引用不续"
    print("    ✓ 选择规则:credential+被引用→续;manual 或未引用→不续")
    print("\n全部通过 ✅  —— 登录态自动续期的选择逻辑就位(真实重登复用 ensure_session)")


if __name__ == "__main__":
    main()
