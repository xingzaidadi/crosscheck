"""
幂等不变量判据 验证(离线、零业务)。
跑:python tests/test_idempotent.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.invariants import idempotent_ok  # noqa: E402


def main():
    print("幂等不变量判据 验证:\n")
    assert idempotent_ok("REQ001", "REQ001") is True
    assert idempotent_ok("REQ001", "REQ002") is False
    assert idempotent_ok("", "") is False and idempotent_ok(None, None) is False
    print("    ✓ 同单据→幂等;不同单据/空→没幂等(重复建单,判失败)")
    print("\n全部通过 ✅  —— 幂等不变量就位(同参两次返回同一单据才算幂等)")


if __name__ == "__main__":
    main()
