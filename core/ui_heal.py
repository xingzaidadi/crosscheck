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


_CANDIDATE_JS = r"""
() => {
  const ctrls = Array.from(document.querySelectorAll('input,textarea,select'));
  return ctrls.slice(0, 60).map((c, i) => {
    if (!c.id) c.setAttribute('data-cc', 'cc' + i);
    const sel = c.id ? ('#' + c.id) : ('[data-cc="cc' + i + '"]');
    const item = c.closest('[class*="form-item"],[class*="form_item"],.form-item,div,td');
    const near = item ? (item.innerText || '').trim().slice(0, 40) : '';
    return {selector: sel, tag: c.tagName.toLowerCase(), type: (c.getAttribute('type')||''),
            placeholder: c.placeholder || '', aria: c.getAttribute('aria-label') || '', near: near};
  });
}
"""


def resolve_input(page, label: str, ui: dict | None = None, llm_resolver=None):
    """返回 (控件 locator 或 None, 策略名)。按稳→兜底顺序找 label 对应的 input/textarea。
    确定性策略全失败且给了 llm_resolver 时,收集候选控件交 LLM 选一个(策略名 'llm');
    llm_resolver(label, candidates)->CSS选择器或None,由调用方(skill 的会话 LLM)注入,默认不启用。"""
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

    # 确定性全失败 → 可选 LLM 重解析(把候选控件 + 其附近文本交给 LLM 选一个)
    if llm_resolver is not None:
        try:
            candidates = page.evaluate(_CANDIDATE_JS)
            sel = llm_resolver(label, candidates)
            if sel:
                loc = page.locator(sel)
                if _cnt(loc):
                    return loc.first, "llm"
        except Exception:  # noqa: BLE001  LLM 兜底失败不炸,返回未命中
            pass

    return None, ""
