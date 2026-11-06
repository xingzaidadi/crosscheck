"""
UI 字段状态断言(通用):验"某字段被联动带出成期望值"+"字段是否只读/不可编辑"。
字段联动/只读类用例(选触发项带出关联字段、并锁定不可编辑…)是前端行为,后端不补,
只能在页面上验:取该标签对应控件的当前值 + 可编辑态,与预期比。配合 ui_actions 回放用。

field_asserts(spec.ui.field_asserts):
  [{label: 字段标签, equals?: 期望值(含即算命中), readonly?: true/false 期望只读态}]
"""
from __future__ import annotations

from core.discovery.fields import DEFAULT_UI

_FIELD_STATE_JS = r"""
(args) => {
  const {label, ui} = args;
  const items = Array.from(document.querySelectorAll(ui.form_item));
  let item = null;
  for (const it of items) {
    const lab = it.querySelector(ui.label);
    const t = lab ? (lab.innerText||'').replace(/[*＊]/g,'').trim() : '';
    if (t === label) { item = it; break; }
  }
  if (!item) return {found:false};
  const ctrl = item.querySelector('input,textarea,select');
  if (ctrl) {
    let val = ctrl.tagName === 'SELECT'
      ? ((ctrl.options[ctrl.selectedIndex]||{}).text || ctrl.value) : ctrl.value;
    const editable = !(ctrl.disabled || ctrl.readOnly || ctrl.getAttribute('aria-disabled') === 'true');
    return {found:true, value:(val||'').trim(), editable:editable};
  }
  // 无输入控件 = 只读展示:取 item 内除 label 外的文本当值
  const labtxt = (item.querySelector(ui.label)||{}).innerText || '';
  let txt = (item.innerText||'').trim();
  if (labtxt) txt = txt.replace(labtxt, '').trim();
  return {found:true, value:txt, editable:false};
}
"""


def check_fields(page, asserts: list[dict], ui: dict | None = None) -> tuple[bool, dict]:
    """逐字段验 值/只读态,返回 (ok, 报告层)。"""
    ui = ui or DEFAULT_UI
    cols = ["字段", "预期值", "实际值", "只读预期", "只读实际", "一致"]
    rows, ok_all = [], True
    for a in asserts:
        label = a.get("label", "")
        st = page.evaluate(_FIELD_STATE_JS, {"label": label, "ui": ui})
        if not st or not st.get("found"):
            ok_all = False
            rows.append([label, a.get("equals", "—"), "(字段未找到)", a.get("readonly", "—"), "—", "✗"])
            continue
        val = st.get("value", "")
        editable = st.get("editable", True)
        ok = True
        if "equals" in a:
            exp = str(a["equals"])
            if not (exp == val or exp in val):
                ok = False
        ro_exp = "—"
        ro_act = "是" if not editable else "否"
        if "readonly" in a:
            ro_exp = "是" if a["readonly"] else "否"
            if bool(a["readonly"]) != (not editable):
                ok = False
        ok_all = ok_all and ok
        rows.append([label, a.get("equals", "—"), val, ro_exp, ro_act, "✓" if ok else "✗"])
    return ok_all, {"name": "UI 字段联动/只读校验", "ok": ok_all,
                    "expected": "联动字段带出期望值且只读态符合预期", "cols": cols, "rows": rows}
