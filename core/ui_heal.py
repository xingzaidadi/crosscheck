"""
选择器自愈(通用):按标签定位输入控件时,主策略失效就依次退到备用策略,
返回定位到的控件 + 用了哪条策略。页面结构变了(去掉 form-item 包裹、换成裸 label、
只剩 placeholder…)也能找回控件;回放端据"用了非主策略"记一次自愈,回写知识待审。

策略顺序(由稳到兜底):
  1 form-item   : form-item 容器(has_text 标签)里的 input/textarea —— 主策略
  2 label-for   : <label for=id> → #id
  3 label-sibling: <label>标签</label> 之后第一个 input
  4 placeholder : 占位符含标签文本
  5 aria-label  : [aria-label=标签]
"""
from __future__ import annotations

from core.discovery.fields import DEFAULT_UI


def _cnt(loc) -> int:
    try:
        return loc.count()
    except Exception:  # noqa: BLE001
        return 0


def resolve_input(page, label: str, ui: dict | None = None):
    """返回 (控件 locator 或 None, 策略名)。按稳→兜底顺序找 label 对应的 input/textarea。"""
    ui = ui or DEFAULT_UI

    item_input = page.locator(ui["form_item"]).filter(has_text=label).first.locator("input, textarea")
    if _cnt(item_input):
        return item_input.first, "form-item"

    lab = page.locator("label").filter(has_text=label).first
    if _cnt(lab):
        try:
            for_id = lab.get_attribute("for")
        except Exception:  # noqa: BLE001
            for_id = None
        if for_id:
            byid = page.locator(f"#{for_id}")
            if _cnt(byid):
                return byid.first, "label-for"
        sib = lab.locator("xpath=following::input[1] | following::textarea[1]")
        if _cnt(sib):
            return sib.first, "label-sibling"

    ph = page.get_by_placeholder(label, exact=False)
    if _cnt(ph):
        return ph.first, "placeholder"

    al = page.locator(f'[aria-label="{label}"]')
    if _cnt(al):
        return al.first, "aria-label"

    return None, ""
