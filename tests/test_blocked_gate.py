"""
待确认口径门禁 验证(离线、零业务):依赖未确认规则的用例被标阻塞,执行绝不判 PASS。
对应改造方案"待确认口径由备注升级为执行门禁"。

跑:python tests/test_blocked_gate.py
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

from core.spec import from_raw  # noqa: E402


def _raw(**kw):
    d = dict(case_id="T", name="用例", level="P0", category="", module="/m",
             preconditions="", steps_text="", expected_text="", notes="", row=1)
    d.update(kw)
    return SimpleNamespace(**d)


def main():
    print("待确认口径门禁 验证:\n")
    b1 = from_raw(_raw(notes="状态枚举待确认"))
    assert b1.blocked, "备注含待确认应阻塞"
    b2 = from_raw(_raw(expected_text="按规则拦截(规则待确认)"))
    assert b2.blocked, "预期含待确认应阻塞"
    print("    ✓ 步骤/预期/备注含'待确认'→ 标记阻塞")

    ok = from_raw(_raw(notes="", expected_text="落库 status=DRAFT"))
    assert not ok.blocked, "口径明确的不该阻塞"
    print("    ✓ 口径明确的用例 → 不阻塞,照常执行")
    print("\n全部通过 ✅  —— 待确认口径门禁就位(未定规则的用例阻塞验收,绝不冒充通过)")


if __name__ == "__main__":
    main()
