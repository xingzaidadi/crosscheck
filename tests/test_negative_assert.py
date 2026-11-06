"""
负向响应断言 验证(离线):response_assert.rejected —— 预期被拒。
守卫/校验/乐观锁冲突类用例多是"预期拒绝/数据不变",需要"响应为失败"的断言,而非字段相等。

跑:python tests/test_negative_assert.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.verifier import Verifier  # noqa: E402
from core.interfaces import TestCase, Expected, ActionResult  # noqa: E402


def _case(ra):
    return TestCase(case_id="N", feature="", account_ref="", data_prep=None, steps=[],
                    expected=Expected(), raw={"response_assert": ra})


def main():
    print("负向响应断言 验证:\n")
    v = Verifier(None)

    ok, _ = v._verify_response(_case({"rejected": True}), ActionResult(ok=True, api_body={"code": 0}))
    assert not ok, "业务成功却预期被拒 → 应失败"
    ok, _ = v._verify_response(_case({"rejected": True}),
                               ActionResult(ok=True, api_body={"code": -1, "message": "状态不允许"}))
    assert ok, "业务 code=-1 被拒 → 应通过"
    ok, _ = v._verify_response(_case({"rejected": True}), ActionResult(ok=False, api_status=400))
    assert ok, "HTTP 400 被拒 → 应通过"
    print("    ✓ rejected:true —— 成功判失败;业务码拒/HTTP 拒 判通过")

    # 不影响正向断言
    ok, _ = v._verify_response(_case({"body": {"code": 0}}), ActionResult(ok=True, api_body={"code": 0}))
    assert ok
    ok, _ = v._verify_response(_case({"body": {"code": 0}}), ActionResult(ok=True, api_body={"code": 5}))
    assert not ok
    print("    ✓ 不影响原正向字段断言")
    print("\n全部通过 ✅  —— 负向响应断言(预期被拒)就位,解锁守卫/校验/冲突类")


if __name__ == "__main__":
    main()
