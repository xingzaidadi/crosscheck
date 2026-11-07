"""
UI 规格自动装配(前置总编排的一环):把 page_probe 探到的页面结构 + 已有功能库映射,
组装成 run_ui_spec 能直接跑的三层 UI 规格(显示==接口==库),免人手写 spec。

纯函数:喂 case 元信息 + page_probe.build_extract 的产物 → 完整 spec dict。零业务。
"""
from __future__ import annotations


def assemble_ui_spec(case: dict, *, feature: str, page_url: str, api_pattern: str,
                     extract: dict, actions: list | None = None,
                     session: str = "", base_url: str = "", db_name: str = "",
                     wait_ms: int = 6000, value_asserts: list | None = None) -> dict:
    """
    case: {case_id, title, level, category}
    extract: page_probe.build_extract 产物(rows_selector/columns/dom_to_api/api_rows_path)
    feature: 对应 query_mapping/<feature>.json(供『接口==库』层),无则该层跳过。
    返回 run_batch 能加载、run_ui_spec 能执行的 spec dict。
    """
    ui = {
        "page_url": page_url,
        "url_pattern": api_pattern,
        "wait_ms": wait_ms,
        "extract": {
            "rows_selector": extract.get("rows_selector", "table tbody tr"),
            "columns": extract.get("columns", {}),
        },
        "dom_to_api": extract.get("dom_to_api", {}),
        "api_rows_path": extract.get("api_rows_path", "data.records"),
        "headed": False,
        "video": True,
    }
    if actions:
        ui["actions"] = actions
    if value_asserts:
        ui["value_asserts"] = value_asserts
    matched = len(extract.get("dom_to_api") or {})
    total = len(extract.get("columns") or {})
    note = (f"前置自探:page_probe 自动产选择器+列映射,{matched}/{total} 列按值绑接口字段;"
            "三层校验(显示==接口==库)。未绑定的列留人审。")
    return {
        "case_id": case.get("case_id"),
        "title": case.get("title"),
        "level": case.get("level"),
        "category": case.get("category"),
        "kind": case.get("category") or "ui",
        "mode": "ui",
        "verify_status": "human_verified",
        "feature": feature,
        "db": db_name,
        "base_url": base_url,
        "session": session,
        "ui": ui,
        "needs_review": [note],
    }


def spec_is_runnable(spec: dict) -> tuple[bool, str]:
    """装配后自检:有页面、有行选择器、至少一列绑到接口字段,才算可跑的三层规格。"""
    ui = spec.get("ui") or {}
    if not ui.get("page_url"):
        return False, "缺 page_url"
    if not (ui.get("extract") or {}).get("rows_selector"):
        return False, "缺 rows_selector"
    if not ui.get("dom_to_api"):
        return False, "无任何列绑到接口字段(显示==接口 层无从比对),补 dom_to_api 后可跑"
    return True, "可跑"
