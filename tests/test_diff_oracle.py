"""差异测试 oracle 验证(离线、零业务):验旧系统即 oracle 的逐字段比对。
跑:python tests/test_diff_oracle.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.diff_oracle import diff_payloads, diff_selected  # noqa: E402


def main():
    print("差异测试 oracle 验证:\n")

    # 完全一致 → consistent
    a = {"code": 0, "data": {"total": 3, "list": [{"id": 1, "v": "x"}]}}
    r = diff_payloads(a, dict(a) if not isinstance(a, dict) else {"code": 0, "data": {"total": 3, "list": [{"id": 1, "v": "x"}]}})
    assert r.consistent and r.diff_count if hasattr(r, "diff_count") else True
    r = diff_payloads(a, {"code": 0, "data": {"total": 3, "list": [{"id": 1, "v": "x"}]}})
    assert r.consistent, r.to_dict()
    print("    ✓ 两系统完全一致 → consistent=True,无差异")

    # 一个字段值不同 → 报该字段差异
    b = {"code": 0, "data": {"total": 3, "list": [{"id": 1, "v": "y"}]}}
    r = diff_payloads(a, b)
    assert not r.consistent
    paths = [d.path for d in r.diffs]
    assert "data.list.0.v" in paths, paths
    print("    ✓ 值不同 → 精确定位到 data.list.0.v 的差异")

    # 新系统少了字段 / 多了字段 → 都报
    r = diff_payloads({"a": 1, "b": 2}, {"a": 1})
    assert not r.consistent and any(d.path == "b" for d in r.diffs)
    r = diff_payloads({"a": 1}, {"a": 1, "c": 9})
    assert not r.consistent and any(d.path == "c" for d in r.diffs)
    print("    ✓ 字段缺失/新增都能报(baseline/candidate 任一侧缺失)")

    # ignore_paths:忽略时间戳/自增 id 噪声
    base = {"id": 1, "name": "n", "updateTime": "2020-01-01"}
    cand = {"id": 2, "name": "n", "updateTime": "2026-11-24"}
    r = diff_payloads(base, cand, ignore_paths={"id", "updateTime"})
    assert r.consistent, r.to_dict()
    assert "id" in r.ignored and "updateTime" in r.ignored
    print("    ✓ ignore_paths 白名单:忽略 id/updateTime 噪声后判一致")

    # 列表下标通配:ignore "updateTime" 命中 list.0.updateTime
    base = {"list": [{"id": 1, "updateTime": "a"}, {"id": 2, "updateTime": "b"}]}
    cand = {"list": [{"id": 1, "updateTime": "X"}, {"id": 2, "updateTime": "Y"}]}
    r = diff_payloads(base, cand, ignore_paths={"updateTime"})
    assert r.consistent, r.to_dict()
    print("    ✓ ignore 通配命中列表内每个元素的 updateTime")

    # 数值/字符串宽松相等(复用 verifier._eq):3 == "3"
    r = diff_payloads({"total": 3}, {"total": "3"})
    assert r.consistent
    print("    ✓ 复用 verifier._eq:3 与 '3' 视为一致(跨源类型宽松)")

    # 定向抽样比对:只看指定路径
    r = diff_selected({"data": {"total": 3, "noise": 1}},
                      {"data": {"total": 3, "noise": 999}},
                      paths=["data.total"])
    assert r.consistent, r.to_dict()
    r = diff_selected({"data": {"total": 3}}, {"data": {"total": 4}}, paths=["data.total"])
    assert not r.consistent
    print("    ✓ diff_selected:只比对指定点路径,噪声字段不参与")

    print("\n全部通过 ✅  —— 旧系统即 oracle,迁移/回归无需人工写断言")


if __name__ == "__main__":
    main()
