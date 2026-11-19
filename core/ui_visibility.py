"""UI 元素可见性断言(通用、零业务)。

验"某命名控件在当前页面上是否可见/存在"。常见于按钮/链接/标签的显示规则:
某条件下按钮应显示、另一条件下不显示。纯前端行为,后端不落库,只能在页面上验。

visibility_asserts(spec.ui.visibility_asserts):
  [{label?: 控件文本(精确或包含), selector?: CSS 选择器, present?: true/false(默认 true),
    enabled?: true/false(可选，仅在控件可见时校验),
    role?: aria role 名(可选辅助定位)}]

每项只需给 label 或 selector 其中一个;两个都给时 selector 优先。
"""
from __future__ import annotations

_VIS_JS = r"""
(args) => {
  const {label, selector, role} = args;
  // selector 优先
  if (selector) {
    const el = document.querySelector(selector);
    if (!el) return {found: false};
    const r = el.getBoundingClientRect();
    const visible = r.width > 0 && r.height > 0 &&
      window.getComputedStyle(el).display !== 'none' &&
      window.getComputedStyle(el).visibility !== 'hidden' &&
      parseFloat(window.getComputedStyle(el).opacity) > 0;
    const enabled = !el.disabled && el.getAttribute('aria-disabled') !== 'true' &&
      !el.classList.contains('hi-v5-button--disabled');
    return {found: true, visible: visible, enabled: enabled};
  }
  // 文本 + 可选 role
  if (!label) return {found: false};
  const lc = label.toLowerCase();
  let els = Array.from(document.querySelectorAll(role ? `[role="${role}"]` : 'button,a,[role="button"],[role="link"],label,span,div'));
  // 也搜全部文本节点含 label 的可见元素
  if (!role) els = Array.from(document.querySelectorAll('*')).filter(e => {
    const t = (e.innerText || '').trim().toLowerCase();
    return t === lc || t.includes(lc);
  });
  for (const el of els) {
    const t = (el.innerText || el.textContent || '').trim().toLowerCase();
    if (t === lc || t.includes(lc)) {
      const r = el.getBoundingClientRect();
      const vis = r.width > 0 && r.height > 0 &&
        window.getComputedStyle(el).display !== 'none' &&
        window.getComputedStyle(el).visibility !== 'hidden' &&
        parseFloat(window.getComputedStyle(el).opacity) > 0;
      const enabled = !el.disabled && el.getAttribute('aria-disabled') !== 'true' &&
        !el.classList.contains('hi-v5-button--disabled');
      return {found: true, visible: vis, enabled: enabled};
    }
  }
  return {found: false};
}
"""


def check_visibility(page, asserts: list[dict]) -> tuple[bool, dict]:
    """逐项验元素可见/不可见,返回 (ok, 报告层)。

    asserts 每项:
      {label?: str, selector?: str, role?: str, present?: bool (default True), enabled?: bool}
    """
    cols = ["控件", "期望", "实际", "一致"]
    rows, ok_all = [], True
    for a in asserts:
        label = a.get("label") or a.get("selector") or "(unnamed)"
        want_present = bool(a.get("present", True))
        st = page.evaluate(_VIS_JS, {
            "label": a.get("label", ""),
            "selector": a.get("selector", ""),
            "role": a.get("role", ""),
        })
        found = bool(st.get("found"))
        visible = found and bool(st.get("visible", True))
        enabled = visible and bool(st.get("enabled", True))
        # 对于 present=True: 元素存在且可见 → 通过; present=False: 不存在或不可见 → 通过
        ok = visible if want_present else not visible
        expected_enabled = a.get("enabled")
        if ok and want_present and expected_enabled is not None:
            ok = enabled == bool(expected_enabled)
        ok_all = ok_all and ok
        expected = "可见" if want_present else "不可见/不存在"
        actual = "可见" if visible else ("存在但不可见" if found else "不存在")
        if want_present and expected_enabled is not None:
            expected += "且" + ("可操作" if expected_enabled else "禁用")
            if visible:
                actual += "且" + ("可操作" if enabled else "禁用")
        rows.append([
            label,
            expected,
            actual,
            "✓" if ok else "✗",
        ])
    return ok_all, {
        "name": "UI 元素可见性校验",
        "ok": ok_all,
        "expected": "命名控件按期望显示/隐藏",
        "cols": cols,
        "rows": rows,
    }
