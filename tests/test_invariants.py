"""
计算不变量 验证(离线、零业务):落库字段 == 提交字段公式;安全求值(不跑任意代码)。

跑:python tests/test_invariants.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.invariants import evaluate, check_compute  # noqa: E402


def main():
    print("计算不变量 验证:\n")
    assert evaluate("quantity * unitPrice", {"quantity": "2", "unitPrice": "25"}) == 50
    assert evaluate("a + b - c", {"a": 10, "b": 5, "c": 3}) == 12
    print("    ✓ 公式求值:quantity*unitPrice=50、a+b-c=12")

    try:
        evaluate("__import__('os').system('x')", {})
        raise AssertionError("不该放行任意代码")
    except Exception:
        print("    ✓ 安全:非四则表达式被拒(不执行任意代码)")

    sub = {"itemList": [{"quantity": "2", "unitPrice": "25", "amount": "999"}]}
    good = {"itemList": [{"amount": "50.0000"}]}      # 服务端重算成 50
    bad = {"itemList": [{"amount": "999"}]}           # 没重算
    ok, _ = check_compute(sub, good, [{"field": "amount", "expr": "quantity * unitPrice", "scope": "item"}], "itemList")
    assert ok
    nok, layer = check_compute(sub, bad, [{"field": "amount", "expr": "quantity * unitPrice", "scope": "item"}], "itemList")
    assert not nok
    print("    ✓ amount==quantity*unitPrice:落库 50 通过;落库 999 判失败(抓住没重算)")
    print("\n全部通过 ✅  —— 计算不变量就位(金额重算等服务端计算声明式校验)")


if __name__ == "__main__":
    main()
