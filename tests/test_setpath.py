"""body_set 点路径写值 验证(离线、零业务):支持嵌套 + 列表下标覆盖。

跑:python tests/test_setpath.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.modeler import _set_path, _build_body  # noqa: E402


def main():
    print("body_set 点路径写值 验证:\n")

    body = {"title": "x", "itemList": [{"qty": 1, "price": 9}]}
    _set_path(body, "itemList.0.qty", 2)
    _set_path(body, "itemList.0.price", 25)
    _set_path(body, "itemList.0.amount", 999)
    assert body["itemList"][0] == {"qty": 2, "price": 25, "amount": 999}, body
    print(f"    ✓ 列表下标覆盖: itemList.0 = {body['itemList'][0]}")

    _set_path(body, "meta.source.sys", "AUTOTEST")
    assert body["meta"]["source"]["sys"] == "AUTOTEST", body
    print("    ✓ 深层缺省自动建 dict: meta.source.sys")

    _set_path(body, "itemList.2.qty", 7)
    assert body["itemList"][2] == {"qty": 7} and body["itemList"][1] == {}, body
    print("    ✓ 列表自动补位到下标 2(中间补空 dict)")

    # 经 _build_body 端到端:模板 + body_set 点路径
    import json, tempfile
    tpl = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump({"requestTitle": "t", "itemList": [{"id": 1, "quantity": 1, "unitPrice": 0, "amount": 0}]}, tpl)
    tpl.close()
    out = _build_body({"template": tpl.name, "item_key": "itemList", "item_drop": ["id"],
                       "body_set": {"itemList.0.quantity": 2, "itemList.0.unitPrice": 25, "itemList.0.amount": 999}})
    assert out["itemList"][0] == {"quantity": 2, "unitPrice": 25, "amount": 999}, out
    print(f"    ✓ _build_body 端到端: itemList.0 = {out['itemList'][0]}(id 已去,值已覆盖)")

    print("\n全部通过 ✅  —— 写入造数可覆盖任意层/列表字段(服务端重算类用例就能建模)")


if __name__ == "__main__":
    main()
