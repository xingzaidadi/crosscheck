"""
Excel 用例接入 + 建模草拟 验证(中性样例,不碰真实用例库)。
临时写一个 11 列格式的小 xlsx,读进来 → 草拟成 ExecSpec,证明:
  1. read_cases 按固定列读出 RawCase(case_id/category 正确);
  2. from_raw 能确定性分类(写/查)、抽接口路径、标 draft 待审。

跑:python tests/test_case_source.py
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

from core.case_source import read_cases  # noqa: E402
from core.spec import from_raw  # noqa: E402

HEADER = ["用例名称", "用例等级", "所属模块", "标签", "前置条件", "备注",
          "步骤描述", "预期结果", "编辑模式", "责任人(名称)", "责任人(ID)"]
ROWS = [
    ["TC01-新建条目-保存生成草稿", "P0", "/示例系统/条目管理/创建", "", "1. 已登录", "",
     "1. 调用 /item/api/item/draft 保存", "1. 返回 code=200,version+1", "TEXT", "测试员", "1001"],
    ["TC02-条目列表-多条件筛选分页", "P1", "/示例系统/条目管理/查询", "", "1. 列表页已打开", "口径待确认",
     "1. 调用 /item/api/item/list 带筛选", "1. 返回 total 与库一致", "TEXT", "测试员", "1001"],
]


def _make_xlsx(path: str):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "测试用例"
    ws.append(HEADER)
    for r in ROWS:
        ws.append(r)
    wb.save(path)


def main():
    print("Excel 用例接入 + 建模草拟 验证:\n")
    with tempfile.TemporaryDirectory() as d:
        xlsx = os.path.join(d, "cases.xlsx")
        _make_xlsx(xlsx)

        cases = read_cases(xlsx)
        assert len(cases) == 2, f"应读到 2 条,实际 {len(cases)}"
        assert cases[0].case_id == "TC01", cases[0].case_id
        assert cases[0].category == "条目管理/创建", cases[0].category
        assert "/item/api/item/draft" in cases[0].steps_text
        assert cases[1].case_id == "TC02" and cases[1].level == "P1"
        print(f"    ✓ read_cases 读出 {len(cases)} 条,case_id/等级/模块末级解析正确")

        s0 = from_raw(cases[0])
        assert s0.kind == "write" and s0.mode == "api", (s0.kind, s0.mode)
        assert "/item/api/item/draft" in s0.endpoints, s0.endpoints
        assert s0.verify_status == "draft"
        print("    ✓ from_raw: 新建类 → write/api,抽出接口路径,标 draft 待审")

        s1 = from_raw(cases[1])
        assert s1.kind == "query" and s1.mode == "reconcile", (s1.kind, s1.mode)
        assert "/item/api/item/list" in s1.endpoints, s1.endpoints
        assert any("待确认" in n for n in s1.needs_review), s1.needs_review
        print("    ✓ from_raw: 查询类 → query/reconcile,口径待确认已标注")

    print("\n全部通过 ✅  —— 固定格式 Excel 能读进来并确定性草拟成可执行规格骨架")


if __name__ == "__main__":
    main()
