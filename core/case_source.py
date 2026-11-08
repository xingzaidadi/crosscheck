"""用例接入层:把各种格式的用例文件读成 RawCase(散文原样,不做语义解析)。

用例是业务数据,通常放 <workspace>/cases/。本模块只负责"读进来";建模成可执行规格
(ExecSpec)是 core/spec.py 的事。

格式可插拔(按扩展名分发,表头/键按名匹配,缺列容错,顺序无所谓):
  .xlsx/.xlsm —— 表头行 + 数据行
  .csv        —— 表头行 + 数据行
  .json       —— 对象数组,键用 RawCase 字段名或同义表头
列名/键名既认 RawCase 字段名(name/steps_text…),也认中文表头(用例名称/步骤描述…)。
"""
from __future__ import annotations

from dataclasses import dataclass, fields as _dc_fields
from pathlib import Path
from typing import Any, Callable

# 中文表头 → RawCase 字段(两侧空白 strip)
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
    row: int = 0            # 源文件行号/序号,便于回溯

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


_FIELDS = {f.name for f in _dc_fields(RawCase)}


def _norm_key(h: Any) -> str | None:
    """表头/键 → RawCase 字段名:既认中文表头,也认字段名本身;认不出返回 None。"""
    if h is None:
        return None
    k = str(h).strip()
    if k in COLUMN_MAP:
        return COLUMN_MAP[k]
    if k in _FIELDS:
        return k
    return None


def _case_from_dict(d: dict, row: int) -> RawCase | None:
    """{RawCase字段: 值} → RawCase(name 必填);非字段键已在上游过滤。"""
    name = str(d.get("name", "") or "").strip()
    if not name:
        return None
    vals = {k: (str(v).strip() if v is not None else "") for k, v in d.items() if k in _FIELDS and k != "row"}
    vals["name"] = name
    vals["row"] = row
    return RawCase(**vals)


def _read_xlsx(path: str | Path, sheet: str | None = None) -> list[RawCase]:
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[sheet] if sheet else wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    header = next(rows, None)
    if not header:
        wb.close()
        return []
    idx = {}
    for i, h in enumerate(header):
        key = _norm_key(h)
        if key:
            idx[key] = i
    if "name" not in idx:
        wb.close()
        raise ValueError(f"用例文件缺必需列 '用例名称'/name;实际表头={list(header)}")
    out = []
    for rn, row in enumerate(rows, start=2):
        d = {k: (row[i] if i < len(row) else None) for k, i in idx.items()}
        c = _case_from_dict(d, rn)
        if c:
            out.append(c)
    wb.close()
    return out


def _read_csv(path: str | Path, sheet: str | None = None) -> list[RawCase]:
    import csv
    out = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            return []
        idx = {}
        for i, h in enumerate(header):
            key = _norm_key(h)
            if key:
                idx[key] = i
        if "name" not in idx:
            raise ValueError(f"CSV 缺必需列 '用例名称'/name;实际表头={header}")
        for rn, row in enumerate(reader, start=2):
            d = {k: (row[i] if i < len(row) else None) for k, i in idx.items()}
            c = _case_from_dict(d, rn)
            if c:
                out.append(c)
    return out


def _read_json(path: str | Path, sheet: str | None = None) -> list[RawCase]:
    import json
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("cases") or data.get("data") or []
    out = []
    for rn, item in enumerate(data or [], start=1):
        if not isinstance(item, dict):
            continue
        d = {}
        for k, v in item.items():
            nk = _norm_key(k)
            if nk:
                d[nk] = v
        c = _case_from_dict(d, rn)
        if c:
            out.append(c)
    return out


READERS: dict[str, Callable[..., list[RawCase]]] = {
    ".xlsx": _read_xlsx, ".xlsm": _read_xlsx, ".xltx": _read_xlsx,
    ".csv": _read_csv, ".json": _read_json,
}


def read_cases(path: str | Path, sheet: str | None = None) -> list[RawCase]:
    """按扩展名分发读用例 → RawCase 列表。未知扩展名按 Excel 尝试(向后兼容)。"""
    reader = READERS.get(Path(path).suffix.lower(), _read_xlsx)
    return reader(path, sheet)
