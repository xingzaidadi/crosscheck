"""用例读取插件 验证(离线、零业务):json/csv 读取 + 中文表头/字段名双认 + 向后兼容。
跑:python tests/test_case_readers.py
"""
from __future__ import annotations

import os
import sys
import json
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.case_source import read_cases  # noqa: E402


def main():
    print("用例读取插件 验证:\n")
    d = tempfile.mkdtemp()

    # JSON:键用字段名 + 中文表头混用
    jp = os.path.join(d, "cases.json")
    json.dump([
        {"name": "TC01-建单", "steps_text": "调接口", "预期结果": "落库 1 条"},
        {"用例名称": "TC02-查询", "module": "列表/检索"},
        {"foo": "bar"},  # 无 name → 跳过
    ], open(jp, "w", encoding="utf-8"), ensure_ascii=False)
    cs = read_cases(jp)
    assert [c.case_id for c in cs] == ["TC01", "TC02"], [c.case_id for c in cs]
    assert cs[0].expected_text == "落库 1 条" and cs[0].steps_text == "调接口"
    assert cs[1].category == "列表/检索"
    print(f"    ✓ JSON:字段名/中文表头双认,无 name 跳过 → {[c.case_id for c in cs]}")

    # CSV:中文表头,列序打乱
    cp = os.path.join(d, "cases.csv")
    open(cp, "w", encoding="utf-8").write("步骤描述,用例名称,预期结果\n点一下,TC09-动作,成功\n")
    cs2 = read_cases(cp)
    assert len(cs2) == 1 and cs2[0].case_id == "TC09" and cs2[0].steps_text == "点一下"
    print("    ✓ CSV:中文表头、列序无关")

    # 缺 name 列 → 报错
    bad = os.path.join(d, "bad.csv")
    open(bad, "w", encoding="utf-8").write("甲,乙\n1,2\n")
    try:
        read_cases(bad)
        raise AssertionError("应因缺 name 报错")
    except ValueError:
        print("    ✓ 缺必需列 → ValueError")

    print("\n全部通过 ✅  —— 用例读取可插拔(xlsx/csv/json),表头自认,零业务离线可测")


if __name__ == "__main__":
    main()
