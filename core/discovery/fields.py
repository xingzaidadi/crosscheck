"""
前端探针(通用,任意表单):枚举控件(标签/类型/必填/占位/可选值)+ 读校验报错。
选择器按 UI 套件配置,默认覆盖 HiUI/antd(form-item + label + error)与朴素 label+input。
给自发现提供"表单要填什么、怎么填"的前端来源。操作 Playwright page。
"""
from __future__ import annotations

from typing import Any

# 默认选择器(HiUI/antd + 朴素表单)。换 UI 套件改这份即可。
DEFAULT_UI = {
    "control": "input, textarea, select, [role=combobox]",
    "form_item": '[class*="form-item"],[class*="form_item"],.form-item',
    "label": '[class*="label"],label',
    "error": '[class*="error"],[class*="form-item__error"],[class*="form-item__message"],[class*="form-message"],[class*="field__message"]',
}

_DISCOVER_JS = r"""
(ui) => {
  const ctrls = Array.from(document.querySelectorAll(ui.control));
  const seen = new Set(); const out = [];
  for (const c of ctrls) {
    if (c.type === 'hidden') continue;
    const item = c.closest(ui.form_item) || c.parentElement;
    let labEl = item ? item.querySelector(ui.label) : null;
    if (!labEl) { const ps = c.previousElementSibling; if (ps && ps.matches(ui.label)) labEl = ps; }
    const raw = (labEl ? labEl.innerText : (c.getAttribute('aria-label')||'')).trim();
    const label = raw.replace(/[*＊]/g, '').trim();   // 剥掉必填星号,留干净字段名
    const key = label || c.name || c.id || c.placeholder || '';
    if (!key || seen.has(key)) continue; seen.add(key);
    const tag = c.tagName.toLowerCase();
    const control = tag === 'select' ? 'select'
                  : (c.getAttribute('role') === 'combobox' ? 'select'
                  : (c.type === 'checkbox' || c.type === 'radio' ? c.type
                  : (tag === 'textarea' ? 'textarea'
                  : (c.type === 'date' || /date|日期/.test(c.placeholder||'') ? 'date' : (c.type || 'text')))));
    // 必填:form-item 的 label 带 *,或控件 required/aria-required
    const reqMark = (labEl && /[*＊]/.test(labEl.innerText)) ||
                    c.required || c.getAttribute('aria-required') === 'true' ||
                    (item && /[*＊]/.test((item.querySelector(ui.label)||{}).innerText||''));
    const opts = tag === 'select'
      ? Array.from(c.querySelectorAll('option')).map(o => (o.innerText||'').trim()).filter(Boolean)
      : [];
    out.push({label: key, control, required: !!reqMark,
              placeholder: c.placeholder || '', options: opts});
  }
  return out;
}
"""


def discover_fields(page: Any, ui: dict | None = None) -> list[dict]:
    """枚举表单控件 → [{label, control, required, placeholder, options}]。"""
    return page.evaluate(_DISCOVER_JS, ui or DEFAULT_UI)


def read_validation_errors(page: Any, ui: dict | None = None) -> list[str]:
    """读当前页面的校验报错文本(点提交后调用)。"""
    sel = (ui or DEFAULT_UI)["error"]
    errs = page.evaluate(
        """(s) => [...new Set(Array.from(document.querySelectorAll(s))
             .map(e => (e.innerText||'').trim()).filter(t => t && t.length <= 40))]""", sel)
    return errs
