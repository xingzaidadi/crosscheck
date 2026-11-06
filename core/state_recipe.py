"""
状态配方(通用):声明式"要某状态的单,先跑哪几步"。把"前置状态造法"从每条用例手写
data_prep,收敛成按功能一份配方 <workspace>/knowledge_base/state_recipes/<feature>.json,
用例只需声明 prepare_state: <状态名>,框架查配方展开成 data_prep 造出该状态的单(含 capture 抓单号)。

配方格式(业务自管,落 workspace):
  {"states": {
     "DRAFT":           {"steps": [{method,url,body,capture}]},
     "PENDING_APPROVE": {"steps": [ draft..., submit... ]},
     "REJECTED":        {"steps": [ draft..., submit..., <驳回接口> ]}   // 转换接口由 probe/文档拿到
  }}
framework 只做"按状态名取 steps";steps 里的接口/字段全是业务数据,core 不认识。
"""
from __future__ import annotations

import json
from pathlib import Path


def recipe_steps(feature: str, state: str, recipes_dir=None) -> list[dict]:
    """取"造出 <state> 状态单"的步骤(data_prep 列表)。无配方/无该状态 → 空列表。"""
    if not feature or not state:
        return []
    if recipes_dir is None:
        from core.workspace import kb_dir
        recipes_dir = kb_dir() / "state_recipes"
    f = Path(recipes_dir) / f"{feature}.json"
    if not f.exists():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    states = data.get("states", data)
    rec = states.get(state) or {}
    return rec.get("steps") or []


def available_states(feature: str, recipes_dir=None) -> list[str]:
    """该功能已有哪些状态配方(给报错提示/选择)。"""
    if recipes_dir is None:
        from core.workspace import kb_dir
        recipes_dir = kb_dir() / "state_recipes"
    f = Path(recipes_dir) / f"{feature}.json"
    if not f.exists():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    return sorted((data.get("states", data) or {}).keys())
