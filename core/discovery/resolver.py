"""
值解析器(通用):给一个已发现的字段,按来源优先级决定"该填什么值"。
优先级:知识库已学值 > 文档业务口径 > 库枚举/样例 > 前端可选值 > 按类型兜底。
名称/标题类一律用唯一标记(可识别、可清理)。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

_NAME = ("名称", "标题", "title", "name")
_TEXTY = ("描述", "备注", "desc", "note", "remark", "说明")


def resolve_value(field: dict, *, knowledge_field: dict | None = None,
                  docs_hint: Any = None, db_sample: list | None = None,
                  marker: str = "AUTOTEST") -> Any:
    label = field.get("label", "")
    ctrl = field.get("control", "text")
    low = label.lower()

    # 名称/标题 → 唯一标记(造数可识别/可清理)
    if any(h in low or h in label for h in _NAME):
        return marker
    # 知识库已学值
    if knowledge_field and knowledge_field.get("value_hint") not in (None, ""):
        return knowledge_field["value_hint"]
    # 文档业务口径给的值
    if docs_hint not in (None, ""):
        return docs_hint
    # 前端可选值:跳过"请选择"类占位,取第一个真实项
    for o in field.get("options") or []:
        if o and not o.startswith("请") and o not in ("--", "-"):
            return o
    # 库样例/枚举
    if db_sample:
        return db_sample[0]
    # 按控件类型兜底
    if ctrl == "number":
        return "1"
    if ctrl == "date":
        return (date.today() + timedelta(days=7)).strftime("%Y-%m-%d")
    if any(h in label for h in _TEXTY):
        return marker
    return marker
