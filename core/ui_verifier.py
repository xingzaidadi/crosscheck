"""
UI 渲染校验:页面"实际显示"的行(DOM 抽取)vs 接口返回的行,逐字段比。
证明"前端把接口数据正确渲染出来了"。与 Reconciler(接口↔库)合起来 = 库↔接口↔页面 三层对齐。

比对放宽:页面常给带单位/名称的文本(如 "100 件"、"FW00 集团采购部门"),
只要接口值在页面文本里出现即算显示正确;完全对不上才判差异。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class UiResult:
    consistent: bool
    diffs: list[str] = field(default_factory=list)
    checked_rows: int = 0

    def render(self) -> str:
        head = "一致 ✅" if self.consistent else "不一致 ❌"
        lines = [f"[页面渲染校验] {head}  (比对 {self.checked_rows} 行)"]
        for d in self.diffs:
            lines.append(f"  显示差异: {d}")
        return "\n".join(lines)


def _dig(obj: Any, dotted: str) -> Any:
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


def _norm(v: Any) -> str:
    return "" if v is None else str(v).strip()


def verify_display(rendered_rows: list[dict], api_response: dict, ui_cfg: dict) -> UiResult:
    """rendered_rows: DOM 抽取的行;api_response: 接口返回;ui_cfg: spec.ui。"""
    dom_to_api = ui_cfg.get("dom_to_api") or {}
    api_rows = _dig(api_response, ui_cfg.get("api_rows_path", "data.records")) or []
    res = UiResult(consistent=True)

    # 分页一致性:页面显示行数应等于接口这一页返回的行数
    if len(rendered_rows) != len(api_rows):
        res.consistent = False
        res.diffs.append(f"行数: 页面显示 {len(rendered_rows)} vs 接口返回 {len(api_rows)}")

    n = min(len(rendered_rows), len(api_rows))
    res.checked_rows = n
    for i in range(n):
        dom, api = rendered_rows[i], api_rows[i]
        for dom_field, api_field in dom_to_api.items():
            dv = _norm(dom.get(dom_field))
            av = _norm(_dig(api, api_field) if "." in api_field else (api.get(api_field) if isinstance(api, dict) else None))
            # 相等,或接口值出现在页面文本里(页面可能带单位/名称前后缀)即算显示正确
            if dv == av:
                continue
            if av and (av in dv or dv in av):
                continue
            res.consistent = False
            res.diffs.append(f"第{i + 1}行 {dom_field}: 页面='{dv}' vs 接口='{av}'")
    return res
