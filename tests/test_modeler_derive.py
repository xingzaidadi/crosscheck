"""
自动推导(免人工配 route)验证:从库 schema 推导清理子表 + 认出名称类标记字段。
sqlite 离线,表名/字段跟任何业务无关 —— 证明推导是通用的。

跑:python tests/test_modeler_derive.py
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

from sqlalchemy import create_engine, text  # noqa: E402

from core.modeler import _derive_children, _is_name_key  # noqa: E402
from db.client import DbClient  # noqa: E402


def main():
    d = tempfile.mkdtemp()
    dbp = os.path.join(d, "s.db").replace("\\", "/")
    eng = create_engine(f"sqlite:///{dbp}")
    with eng.begin() as c:
        # 主表 + 两张同模块、含父键列的子表;一张同模块但无父键列;一张异模块含同名列
        c.execute(text("CREATE TABLE ord_request (id INTEGER PRIMARY KEY, ord_code TEXT, title TEXT)"))
        c.execute(text("CREATE TABLE ord_item (id INTEGER PRIMARY KEY, ord_code TEXT)"))
        c.execute(text("CREATE TABLE ord_log (id INTEGER PRIMARY KEY, ord_code TEXT)"))
        c.execute(text("CREATE TABLE ord_meta (id INTEGER PRIMARY KEY, x TEXT)"))      # 同模块无父键列
        c.execute(text("CREATE TABLE other_thing (id INTEGER PRIMARY KEY, ord_code TEXT)"))  # 异模块
    eng.dispose()
    db = DbClient(dsn_readonly=f"sqlite:///{dbp}")

    print("自动推导 验证:\n")
    kids = _derive_children(db, "ord_request", "ord_code")
    assert kids == ["ord_item", "ord_log"], kids
    print(f"    ✓ 子表推导: 同模块 + 含父键列 → {kids}(排除无父键列的 ord_meta、异模块 other_thing、主表自身)")

    assert _is_name_key("requestTitle") and _is_name_key("name") and _is_name_key("客户名称")
    assert not _is_name_key("quantity") and not _is_name_key("unitPrice")
    print("    ✓ 标记字段识别: 名称/标题类→是,数量/单价→否")
    db.close()
    print("\n全部通过 ✅  —— 清理子表 + 标记字段 可从 schema/模板自动推导(route 免手列)")


if __name__ == "__main__":
    main()
