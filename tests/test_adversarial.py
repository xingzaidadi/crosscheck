"""
对抗用例生成 验证(离线、零业务):从库约束派生非法输入。

跑:python tests/test_adversarial.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.adversarial import gen_invalid  # noqa: E402


def main():
    print("对抗用例生成 验证:\n")
    cons = {
        "id": {"auto": True, "required": False},
        "name": {"required": True, "type": "varchar", "enum": []},
        "status": {"required": False, "type": "varchar", "enum": ["NEW", "DONE"]},
        "qty": {"required": False, "type": "int", "enum": []},
    }
    inv = gen_invalid(cons)
    cols = {(i["column"], i["kind"]) for i in inv}
    assert ("name", "required") in cols, inv
    assert ("status", "enum") in cols, inv
    assert ("qty", "type") in cols, inv
    assert not any(i["column"] == "id" for i in inv), "自增列不该生成"
    print(f"    ✓ 派生 {len(inv)} 条:必填留空(name)、非法枚举(status)、非数字(qty);自增 id 跳过")
    byn = {i["column"]: i for i in inv}
    assert byn["name"]["value"] == "" and byn["qty"]["value"] == "abc"
    assert byn["status"]["value"] == "__NOT_IN_ENUM__"
    print("    ✓ 非法值与 why 对:留空/非数字/越枚举")
    print("\n全部通过 ✅  —— 对抗/边界用例按库约束自动生成(负向用例不用人写)")


if __name__ == "__main__":
    main()
