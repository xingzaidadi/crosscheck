"""
副作用防护 验证(离线、零业务):前后快照比,抓"不该变却变了"的字段。

跑:python tests/test_unchanged.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.unchanged import render_where, read_fields, diff  # noqa: E402


class FakeDB:
    def __init__(self, row): self.row = row
    def query(self, sql): return [self.row] if self.row else []


def main():
    print("副作用防护 验证:\n")
    assert render_where("t='{{AUTOTEST_标记值}}' AND c={{code}}", "M", {"code": "R1"}) == "t='M' AND c=R1"
    print("    ✓ where 模板:marker 与 {{code}} 都替换")

    snap = read_fields(FakeDB({"status": "PENDING_APPROVE", "title": "T", "id": 1}),
                       "t", "x", fields=["status", "title"])
    assert snap == {"status": "PENDING_APPROVE", "title": "T"}
    print("    ✓ read_fields:按列取快照")

    ok, _ = diff({"status": "PENDING_APPROVE", "title": "T"}, {"status": "PENDING_APPROVE", "title": "T"})
    assert ok
    nok, layer = diff({"status": "PENDING_APPROVE"}, {"status": "TO_ACCEPT"})
    assert not nok and any(r[0] == "status" for r in layer["rows"])
    print("    ✓ 不变→通过;status 被改→判失败(抓副作用)")

    gone, _ = diff({"a": 1}, None)
    assert not gone, "记录消失也算变"
    print("    ✓ 记录前后存在性变化(消失/新增)也算变")
    print("\n全部通过 ✅  —— 副作用防护就位(被拒/守卫操作后数据零变化)")


if __name__ == "__main__":
    main()
