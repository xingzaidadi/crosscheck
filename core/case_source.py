"""
用例接入层:把固定列格式的 Excel 用例读成 RawCase(散文原样,不做语义解析)。

用例是业务数据,通常放 <workspace>/cases/*.xlsx。本模块只负责"读进来",
把散文建模成可执行规格(ExecSpec)是 core/spec.py 的事。

固定列格式(按表头名匹配,缺列容错;列顺序无所谓):
  用例名称 | 用例等级 | 所属模块 | 标签 | 前置条件 | 备注 | 步骤描述 | 预期结果 | 编辑模式 | 责任人(名称) | 责任人(ID)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# 表头名 → RawCase 字段。表头两侧空白会被 strip。
COLUMN_MAP = {
    "用例名称": "name",
    "用例等级": "level",
    "所属模块": "module",
    "标签": "tags",
    "前置条件": "preconditions",
    "备注": "notes",
    "步骤描述": "steps_text",
    "预期结果": "expected_text",
    "编辑模式": "edit_mode",
    "责任人(名称)": "owner_name",
    "责任人(ID)": "owner_id",
}


@dataclass
class RawCase:
    name: str
    level: str = ""
    module: str = ""
    tags: str = ""
    preconditions: str = ""
    notes: str = ""
    steps_text: str = ""
    expected_text: str = ""
    edit_mode: str = ""
    owner_name: str = ""
    owner_id: str = ""
    row: int = 0            # Excel 行号,便于回溯

    @property
    def case_id(self) -> str:
        """用例名前缀作 id:'TC01-新建...' → 'TC01';取不到则用整名。"""
        head = self.name.split("-", 1)[0].strip()
        return head or self.name

    @property
    def category(self) -> str:
        """所属模块路径的末两级,如 '模块/子模块'。"""
        parts = [s for s in self.module.replace("\\", "/").split("/") if s.strip()]
        return "/".join(parts[-2:]) if parts else ""


def read_cases(path: str | Path, sheet: str | None = None) -> list[RawCase]:
    """读 Excel → RawCase 列表。第一行为表头,按 COLUMN_MAP 建列索引。"""
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[sheet] if sheet else wb.worksheets[0]

    rows = ws.iter_rows(values_only=True)
    header = next(rows, None)
    if not header:
        return []

    idx: dict[str, int] = {}
    for i, h in enumerate(header):
        key = COLUMN_MAP.get(str(h).strip()) if h is not None else None
        if key:
            idx[key] = i
    if "name" not in idx:
        raise ValueError(f"Excel 缺必需列 '用例名称';实际表头={list(header)}")

    def cell(row: tuple, key: str) -> str:
        i = idx.get(key)
        if i is None or i >= len(row) or row[i] is None:
            return ""
        return str(row[i]).strip()

    cases: list[RawCase] = []
    for rn, row in enumerate(rows, start=2):
        name = cell(row, "name")
        if not name:
            continue
        cases.append(RawCase(
            name=name, level=cell(row, "level"), module=cell(row, "module"),
            tags=cell(row, "tags"), preconditions=cell(row, "preconditions"),
            notes=cell(row, "notes"), steps_text=cell(row, "steps_text"),
            expected_text=cell(row, "expected_text"), edit_mode=cell(row, "edit_mode"),
            owner_name=cell(row, "owner_name"), owner_id=cell(row, "owner_id"), row=rn,
        ))
    wb.close()
    return cases
