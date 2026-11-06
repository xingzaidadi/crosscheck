"""
语义 UI 动作回放(通用,UI 深水区):把页面操作记成"按标签/表头语义定位"的步骤,
回放时**重新观察定位**控件再执行(不记坐标,抗 DOM 漂移;借 dsh record→replay 思路)。
专门处理之前超时的复杂控件:级联下拉、可编辑网格单元格、日期选择。

page_model(存 workspace/knowledge_base/page_model/<feature>.json):一串语义步骤
  [{action, label, value, ...}]:
    text|number|textarea : {action, label, value}         标签定位 input/textarea → fill
    select               : {action, label, value}         原生 select 或自定义下拉(点开选项)
    cascader             : {action, label, path:[l1,l2..]} 级联:点开 → 逐级点选项文本
    date                 : {action, label, value}          直接填 input,失败则点开选当天格
    grid_cell            : {action, column, value, row:0}   可编辑表格:按表头文本定位列、行号定位行 → 激活编辑 → 填
    click                : {action, text|role,name}         语义点击(按钮/链接)
回放纯 Playwright,选择器按 UI 套件配置(复用 DEFAULT_UI),失败逐步返回,供自愈/记账。
"""
from __future__ import annotations

from typing import Any

from core.discovery.fields import DEFAULT_UI


def _item(page, label: str, ui: dict):
    """按标签拿到表单项容器。用 .filter(has_text=) —— 注意 :has-text() 在逗号选择器里只绑最后一个
    分支,会退化成"取第一个 form-item",这里避开那个坑。"""
    return page.locator(ui["form_item"]).filter(has_text=label).first


def _text(page, label, value, ui) -> None:
    it = _item(page, label, ui)
    it.locator("input, textarea").first.fill(str(value), timeout=4000)


def _select(page, label, value, ui) -> None:
    it = _item(page, label, ui)
    native = it.locator("select")
    if native.count():
        native.first.select_option(label=str(value))
        return
    it.click(timeout=3000)                    # 自定义下拉:点开
    page.wait_for_timeout(250)
    page.get_by_text(str(value), exact=True).first.click(timeout=3000)


def _cascader(page, label, path, ui) -> None:
    """级联:点开控件,按 path 逐级点选项文本(多级类目这类)。"""
    _item(page, label, ui).click(timeout=3000)
    page.wait_for_timeout(250)
    for seg in path:
        page.get_by_text(str(seg), exact=True).first.click(timeout=3000)
        page.wait_for_timeout(150)


def _date(page, label, value, ui) -> None:
    """日期:优先直接填 input(多数组件接受键入);失败则点开选面板里当天/匹配格。"""
    it = _item(page, label, ui)
    inp = it.locator("input").first
    try:
        inp.fill(str(value), timeout=2500)
        inp.press("Enter")
        return
    except Exception:  # noqa: BLE001
        inp.click(timeout=2500)
        page.wait_for_timeout(250)
        page.get_by_text(str(value), exact=True).first.click(timeout=2500)


def _grid_cell(page, column, value, ui, row: int = 0) -> None:
    """可编辑网格:按表头文本定位列号,按行号定位行,点开单元格编辑器填值。
    之前通用 td:nth-child 填不中 HiUI 可编辑格 —— 这里先按表头文本算列,再点单元格激活再填。"""
    table = page.locator("table").first
    headers = table.locator("thead th")
    n = headers.count()
    col_idx = None
    for i in range(n):
        if (headers.nth(i).inner_text() or "").strip() == column:
            col_idx = i
            break
    if col_idx is None:
        raise RuntimeError(f"网格找不到列『{column}』")
    cell = table.locator("tbody tr").nth(row).locator("td").nth(col_idx)
    cell.click(timeout=3000)                  # 激活该格的编辑器
    page.wait_for_timeout(150)
    editor = cell.locator("input, textarea")
    if editor.count():
        editor.first.fill(str(value), timeout=3000)
    else:                                     # 编辑器浮在格外(portal),退回页面级 input
        page.locator("input:focus, textarea:focus").first.fill(str(value), timeout=3000)


def _click(page, step, ui) -> None:
    if step.get("role") and step.get("name"):
        page.get_by_role(step["role"], name=step["name"]).first.click(timeout=3000)
    else:
        page.get_by_text(str(step.get("text", "")), exact=True).first.click(timeout=3000)


def replay(page, actions: list[dict], ui: dict | None = None) -> list[dict]:
    """按 page_model 回放一串语义动作,返回每步 {action, target, ok, error}。失败不中断,留给自愈/记账。"""
    ui = ui or DEFAULT_UI
    results = []
    for a in actions:
        act = a.get("action", "text")
        target = a.get("label") or a.get("column") or a.get("text") or a.get("name") or ""
        try:
            if act in ("text", "number", "textarea"):
                _text(page, a["label"], a.get("value", ""), ui)
            elif act == "select":
                _select(page, a["label"], a.get("value", ""), ui)
            elif act == "cascader":
                _cascader(page, a["label"], a.get("path") or [], ui)
            elif act == "date":
                _date(page, a["label"], a.get("value", ""), ui)
            elif act == "grid_cell":
                _grid_cell(page, a["column"], a.get("value", ""), ui, int(a.get("row", 0)))
            elif act == "click":
                _click(page, a, ui)
            else:
                raise RuntimeError(f"未知动作 {act}")
            results.append({"action": act, "target": target, "ok": True, "error": ""})
        except Exception as e:  # noqa: BLE001
            results.append({"action": act, "target": target, "ok": False, "error": str(e)[:120]})
    return results
