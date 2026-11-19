"""
语义 UI 动作回放(通用,UI 深水区):把页面操作记成"按标签/表头语义定位"的步骤,
回放时**重新观察定位**控件再执行(不记坐标,抗 DOM 漂移;借 dsh record→replay 思路)。
专门处理之前超时的复杂控件:级联下拉、可编辑网格单元格、日期选择。

page_model(存 workspace/knowledge_base/page_model/<feature>.json):一串语义步骤
  [{action, label, value, ...}]:
    text|number|textarea : {action, label, value}         标签定位 input/textarea → fill
    select               : {action, label, value}         原生 select 或自定义下拉(点开选项)
    search_select        : {action, label, value?, index?} 搜索型选择器(弹层搜索框+选项,hi-v5 等)
    cascader             : {action, label, path:[l1,l2..]} 级联:点开 → 逐级点选项文本
    date                 : {action, label, value}          直接填 input,失败则点开选当天格
    grid_cell            : {action, column, value, row:0}   可编辑表格:按表头文本定位列、行号定位行 → 激活编辑 → 填
    click                : {action, text|role,name}         语义点击(按钮/链接)
回放纯 Playwright,选择器按 UI 套件配置(复用 DEFAULT_UI),失败逐步返回,供自愈/记账。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from core.discovery.fields import DEFAULT_UI
from core.ui_heal import resolve_input


def _item(page, label: str, ui: dict):
    """按标签拿到表单项容器。用 .filter(has_text=) —— 注意 :has-text() 在逗号选择器里只绑最后一个
    分支,会退化成"取第一个 form-item",这里避开那个坑。"""
    return page.locator(ui["form_item"]).filter(has_text=label).first


def _text(page, label, value, ui, llm_resolver=None) -> str:
    """多策略定位输入控件并填;返回命中的策略名(非 form-item = 发生自愈)。"""
    loc, strat = resolve_input(page, label, ui, llm_resolver)
    if loc is None:
        raise RuntimeError(f"找不到字段『{label}』的输入控件(主/备/LLM 策略均失效)")
    loc.fill(str(value), timeout=4000)
    return strat


def _select(page, label, value, ui) -> None:
    it = _item(page, label, ui)
    native = it.locator("select")
    if native.count():
        native.first.select_option(label=str(value))
        return
    it.click(timeout=3000)                    # 自定义下拉:点开
    page.wait_for_timeout(250)
    page.get_by_text(str(value), exact=True).first.click(timeout=3000)


def _search_select(page, a, ui) -> None:
    """搜索型选择器(hi-v5-picker/fn-search-select 等:点开→弹层搜索框→选项列表→点选)。
    通用:选项挂 body 级弹层(非 form-item 内),选项文本常多行('名称\\n编码'),原生 _select 的
    exact 文本匹配够不着。这里:按 label/placeholder 定位触发点→点开→(可选)搜索框输入过滤→
    点第 index 个(或含 value 文本的)选项→等联动。
    a: {label, value?(搜索/匹配文本), index?(默认0)}。"""
    label = a.get("label", "")
    value = a.get("value")
    idx = int(a.get("index", 0) or 0)
    # 定位触发点:优先 placeholder 含 label,退回当前可见业务项；同页可能有隐藏/虚拟表单副本。
    trig = page.locator(f'[placeholder*="{label}"]')
    candidates = []
    if trig.count():
        candidates.append(trig)
    try:
        item = _item(page, label, ui)
        if item.count():
            candidates.append(item.locator('[class*="picker"],[class*="select"],input,button:visible'))
            candidates.append(item)
    except Exception:
        pass
    # HiUI editable grids render the field label in a line-summary cell rather
    # than a form-item; use the nearest visible cell as a last deterministic fallback.
    text_label = page.get_by_text(str(label), exact=True)
    if text_label.count():
        candidates.append(text_label)
        candidates.append(text_label.last.locator("xpath=ancestor::td[1]"))
    last = None
    for candidate in candidates:
        try:
            loc = candidate.last if hasattr(candidate, "last") else candidate
            loc.wait_for(state="visible", timeout=1200)
            loc.scroll_into_view_if_needed(timeout=1000)
            loc.click(timeout=2500)
            break
        except Exception as exc:  # noqa: BLE001
            last = exc
    else:
        raise RuntimeError(f"找不到可见搜索选择器『{label}』: {str(last)[:120]}")
    page.wait_for_timeout(600)
    # 可见弹层(hi-v5 弹层挂 body);取最后一个可见的下拉/picker 弹层
    popper = page.locator(
        '[class*="picker__popper"]:visible, [class*="select__dropdown"]:visible, '
        '.fn-search-select-overlay:visible, [class*="popper"]:visible').last
    # 有搜索框且给了 value → 过滤
    if value:
        si = popper.locator('input:visible').first
        if si.count():
            si.fill(str(value), timeout=3000)
            page.wait_for_timeout(900)
    # 选项:弹层内 option/item/li;给了 value 优先按文本点,否则点第 idx 个
    picked = False
    if value:
        cand = popper.get_by_text(str(value)).first
        if cand.count():
            cand.click(timeout=4000)
            picked = True
    if not picked:
        opts = popper.locator('[class*="option"]:visible, [class*="item"]:visible, li:visible')
        opts.nth(idx).click(timeout=4000)
    page.wait_for_timeout(800)   # 等联动带出


def _cascader(page, label, path, ui) -> None:
    """级联:点开控件,按 path 逐级点选项文本(多级类目这类)。"""
    _item(page, label, ui).click(timeout=3000)
    page.wait_for_timeout(250)
    for seg in path:
        page.get_by_text(str(seg), exact=True).first.click(timeout=3000)
        page.wait_for_timeout(150)


def _date(page, label, value, ui, llm_resolver=None) -> str:
    """日期:多策略定位 input,优先直接键入;失败则点开选面板里匹配格。返回命中的策略名。"""
    inp, strat = resolve_input(page, label, ui, llm_resolver)
    if inp is None:
        raise RuntimeError(f"找不到日期字段『{label}』")
    try:
        inp.fill(str(value), timeout=2500)
        inp.press("Enter")
    except Exception:  # noqa: BLE001
        inp.click(timeout=2500)
        page.wait_for_timeout(250)
        page.get_by_text(str(value), exact=True).first.click(timeout=2500)
    return strat


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
    """按 role+name 或 text 点击;组件库按钮(图标/嵌套 span/空格文案)常让 role/exact 匹配落空,
    故依次自愈:role+name → text 精确 → text 模糊 → `:has-text` 第一个可见可点元素。"""
    name = step.get("name") or step.get("text") or ""
    attempts = []
    if step.get("selector"):
        attempts.append(lambda: page.locator(str(step["selector"])).first)
    if step.get("role") and step.get("name"):
        attempts.append(lambda: page.get_by_role(step["role"], name=step["name"]).first)
    if step.get("text"):
        attempts.append(lambda: page.get_by_text(str(step["text"]), exact=True).first)
    if name:
        attempts.append(lambda: page.get_by_text(name, exact=False).first)
        # 只认可见的(组件库表格里同名按钮常有隐藏/虚拟行副本,.first 可能命中隐藏的)
        attempts.append(lambda: page.locator(
            f"button:has-text('{name}'):visible, a:has-text('{name}'):visible, "
            f"[role=button]:has-text('{name}'):visible").first)
    last = None
    for mk in attempts:
        try:
            loc = mk()
            loc.wait_for(state="visible", timeout=2500)
            try:
                loc.scroll_into_view_if_needed(timeout=1500)
            except Exception:  # noqa: BLE001
                pass
            loc.click(timeout=2500)
            return
        except Exception as e:  # noqa: BLE001  试下一个定位策略
            last = e
    # 兜底:强制点第一个可见同名元素(越过 antd 遮挡层/动画态)
    if name:
        try:
            page.locator(f":is(button,a,[role=button]):has-text('{name}'):visible").first.click(timeout=2000, force=True)
            return
        except Exception:  # noqa: BLE001
            pass
    raise RuntimeError(f"点击失败(所有定位策略落空): {name!r} · {str(last)[:80]}")


def replay(page, actions: list[dict], ui: dict | None = None, llm_resolver=None) -> list[dict]:
    """按 page_model 回放一串语义动作,返回每步 {action, target, ok, error}。失败不中断,留给自愈/记账。
    llm_resolver 可选:确定性定位失败时交 LLM 重解析(由 skill 的会话 LLM 注入),命中记 heal=llm。"""
    ui = ui or DEFAULT_UI
    results = []
    for a in actions:
        act = a.get("action", "text")
        target = a.get("label") or a.get("column") or a.get("text") or a.get("name") or ""
        try:
            strat = ""
            if act in ("text", "number", "textarea"):
                strat = _text(page, a["label"], a.get("value", ""), ui, llm_resolver)
            elif act == "select":
                _select(page, a["label"], a.get("value", ""), ui)
            elif act == "search_select":
                _search_select(page, a, ui)
            elif act == "cascader":
                _cascader(page, a["label"], a.get("path") or [], ui)
            elif act == "date":
                strat = _date(page, a["label"], a.get("value", ""), ui, llm_resolver)
            elif act == "grid_cell":
                _grid_cell(page, a["column"], a.get("value", ""), ui, int(a.get("row", 0)))
            elif act == "click":
                _click(page, a, ui)
            elif act == "fill":
                # 按 placeholder/selector 直填(搜索框等无 label 的输入);清空后填
                if a.get("placeholder"):
                    loc = page.get_by_placeholder(a["placeholder"], exact=False).first
                else:
                    loc = page.locator(a["selector"]).first
                loc.fill(str(a.get("value", "")), timeout=3000)
            elif act == "upload":
                source = Path(str(a.get("path") or "")).resolve()
                if not source.is_file():
                    raise FileNotFoundError(source)
                if a.get("selector"):
                    loc = page.locator(a["selector"]).first
                elif a.get("label"):
                    loc = _item(page, a["label"], ui).locator('input[type="file"]').first
                else:
                    loc = page.locator('input[type="file"]').first
                loc.set_input_files(str(source), timeout=5000)
                row_extra = {"file": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                             "size": source.stat().st_size}
            elif act == "download":
                output_dir = Path(str(a.get("output_dir") or ".")).resolve()
                output_dir.mkdir(parents=True, exist_ok=True)
                with page.expect_download(timeout=int(a.get("timeout_ms") or 15000)) as info:
                    _click(page, a, ui)
                download = info.value
                suggested = download.suggested_filename
                target_path = output_dir / str(a.get("filename") or suggested)
                download.save_as(str(target_path))
                if a.get("expected_name") and str(a["expected_name"]) != suggested:
                    raise AssertionError(f"download filename: {suggested!r}")
                minimum_size = int(a.get("min_size") or 1)
                if target_path.stat().st_size < minimum_size:
                    raise AssertionError(f"download size below {minimum_size}")
                expected_hash = str(a.get("sha256") or "")
                actual_hash = hashlib.sha256(target_path.read_bytes()).hexdigest()
                if expected_hash and expected_hash != actual_hash:
                    raise AssertionError("download sha256 mismatch")
                row_extra = {"file": str(target_path), "sha256": actual_hash,
                             "size": target_path.stat().st_size}
            elif act == "frame_click":
                frame = page.frame_locator(str(a["frame"]))
                name = str(a.get("name") or a.get("text") or "")
                locator = frame.get_by_role(str(a.get("role") or "button"), name=name,
                                            exact=bool(a.get("exact", True))).first
                locator.click(timeout=int(a.get("timeout_ms") or 5000))
            elif act == "frame_fill":
                frame = page.frame_locator(str(a["frame"]))
                locator = frame.locator(str(a["selector"])).first
                locator.fill(str(a.get("value") or ""), timeout=int(a.get("timeout_ms") or 5000))
            elif act == "press":
                locator = page.locator(str(a.get("selector") or "body")).first
                locator.press(str(a.get("key") or "Enter"), timeout=int(a.get("timeout_ms") or 5000))
            elif act == "hover":
                page.get_by_text(str(a.get("text") or ""), exact=False).first.hover(timeout=5000)
            elif act in {"check", "uncheck"}:
                locator = resolve_input(page, str(a.get("label") or ""), ui, llm_resolver)[0]
                if locator is None:
                    raise RuntimeError(f"找不到复选框字段『{a.get('label')}』")
                if act == "check":
                    locator.check(timeout=5000)
                else:
                    locator.uncheck(timeout=5000)
            elif act == "wait_for":
                if a.get("text"):
                    locator = page.get_by_text(str(a["text"]), exact=bool(a.get("exact", False))).first
                else:
                    locator = page.locator(str(a.get("selector") or "body")).first
                locator.wait_for(state=str(a.get("state") or "visible"),
                                 timeout=int(a.get("timeout_ms") or 10000))
            elif act == "scroll":
                locator = page.locator(str(a.get("selector") or "body")).first
                locator.scroll_into_view_if_needed(timeout=int(a.get("timeout_ms") or 5000))
            elif act == "assert_visible":
                if a.get("text"):
                    loc = page.get_by_text(str(a["text"]), exact=bool(a.get("exact", False))).first
                else:
                    loc = page.locator(str(a["selector"])).first
                loc.wait_for(state="visible", timeout=int(a.get("timeout_ms") or 5000))
            elif act == "wait_ms":
                page.wait_for_timeout(int(a.get("ms") or 1000))
            else:
                raise RuntimeError(f"未知动作 {act}")
            row = {"action": act, "target": target, "ok": True, "error": ""}
            if "row_extra" in locals():
                row.update(row_extra)
                del row_extra
            if strat and strat != "form-item":   # 走了备用策略 = 发生自愈,标出来供回写知识待审
                row["heal"] = strat
            results.append(row)
        except Exception as e:  # noqa: BLE001
            results.append({"action": act, "target": target, "ok": False, "error": str(e)[:120]})
    return results
