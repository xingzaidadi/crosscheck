"""三管齐下·验证层分类(通用、零业务):判定每条用例需要哪几层验证——
  ui(页面展示/交互)· api(接口调用)· db(落库/状态),并归为四类:
    three   三端 UI+API+DB —— 有页面交互又落库(走 UI 三层管线)
    api_db  接口+DB        —— 纯后端守卫/校验/幂等/事件(走 API 引擎)
    ui_only 仅 UI          —— 上传/拖拽/弹窗等无接口可绑(走页面断言)
    todo    待定           —— 无信号,人工判

关键词属业务,放 workspace/config/layer_keywords.yaml;core 不认任何领域词,只做"按规则归层"。
纯函数、可测。换系统改 workspace 关键词即可。
"""
from __future__ import annotations

from typing import Any

CATS = ("three", "api_db", "ui_only", "todo")
CAT_TITLE = {"three": "三端(UI+接口+DB)", "api_db": "接口+DB", "ui_only": "纯UI", "todo": "待定"}


def _load_rules() -> dict:
    """层关键词规则(workspace):{ui:[...], api:[...], db:[...], ui_only:[...]}。core 无则空。"""
    try:
        import yaml
        from core.workspace import config_dir
        p = config_dir() / "layer_keywords.yaml"
        if p.exists():
            return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        pass
    return {}


def classify(prose: str, rules: dict | None = None) -> tuple[str, dict]:
    """(散文, 规则) → (类别, {ui,api,db})。规则空则全 False→todo。"""
    rules = rules if rules is not None else _load_rules()
    ui = any(k in prose for k in (rules.get("ui") or []))
    api = any(k in prose for k in (rules.get("api") or []))
    db = any(k in prose for k in (rules.get("db") or []))
    ui_only = any(k in prose for k in (rules.get("ui_only") or [])) and not (api and db)
    if ui_only:
        return "ui_only", {"ui": True, "api": False, "db": False}
    if ui and (api or db):
        return "three", {"ui": True, "api": api, "db": db}
    if api or db:
        return "api_db", {"ui": False, "api": api, "db": db}
    if ui:
        return "ui_only", {"ui": True, "api": False, "db": False}
    return "todo", {"ui": False, "api": False, "db": False}


def classify_cases(cases: list[Any], rules: dict | None = None) -> dict[str, list]:
    """cases: 带 .case_id/.name/.steps_text/.expected_text/.preconditions 的用例对象。
    → {类别: [(case_id, name)]}。"""
    rules = rules if rules is not None else _load_rules()
    out: dict[str, list] = {c: [] for c in CATS}
    for c in cases:
        blob = " ".join(str(getattr(c, k, "") or "") for k in
                        ("name", "module", "preconditions", "steps_text", "expected_text"))
        cat, _ = classify(blob, rules)
        out[cat].append((getattr(c, "case_id", ""), getattr(c, "name", "")[:40]))
    return out
