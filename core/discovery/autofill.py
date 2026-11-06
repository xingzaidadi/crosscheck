"""
自动填表(通用):按字段标签定位控件并填入解析出的值。文本/数字/文本域直接填;
原生 select 用 select_option;自定义下拉(HiUI/antd)点开再选项。best-effort、可扩展。
配合 fields(发现)+ resolver(决定填什么)+ knowledge(记住),构成自发现填表闭环。
"""
from __future__ import annotations

from typing import Any

from core.discovery.fields import DEFAULT_UI


def fill_field(page: Any, field: dict, value: Any, ui: dict | None = None) -> bool:
    """按标签定位 field 的控件并填 value。返回是否填成功。"""
    ui = ui or DEFAULT_UI
    label = field.get("label", "")
    ctrl = field.get("control", "text")
    if value is None or not label:
        return False
    item = page.locator(ui["form_item"]).filter(has_text=label).first
    try:
        if ctrl in ("text", "number", "textarea"):
            ph = field.get("placeholder")
            if ph:   # 占位符定位最稳(HiUI 控件无稳定 id)
                page.get_by_placeholder(ph).first.fill(str(value), timeout=4000)
                return True
            item.locator("input, textarea").first.fill(str(value), timeout=4000)
            return True
        if ctrl == "select":
            native = item.locator("select")
            if native.count():
                native.first.select_option(label=str(value))
                return True
            # 自定义下拉:点开 → 选项
            item.click(timeout=3000)
            page.wait_for_timeout(400)
            page.get_by_text(str(value), exact=True).first.click(timeout=3000)
            return True
        if ctrl in ("checkbox", "radio"):
            item.locator(f"input[type={ctrl}]").first.check(timeout=3000)
            return True
    except Exception:  # noqa: BLE001  单字段填失败不炸,返回 False 让上层记 miss
        return False
    return False


def autofill(page, fields: list[dict], values: dict, ui: dict | None = None) -> dict:
    """按 values{label:value} 填一批字段,返回 {label: ok}。只填 values 里给了值的。"""
    result = {}
    for f in fields:
        lab = f.get("label")
        if lab in values:
            result[lab] = fill_field(page, f, values[lab], ui)
    return result
