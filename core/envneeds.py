"""通用环境待补清单生成器(零业务):把每条"没通过"的用例按**该谁补**归类——
  tool(工具侧:补路由/建模/录报文就能跑)· env(环境侧:账号/触发/场景/数据/文件)·
  product(产品侧:口径未定义)· defect(已检出缺陷,开发修)。
核心只给"终态 → 泛化归属"的通用映射;业务细化(哪些关键词算"缺某角色账号/缺某场景")
读 workspace/config/env_needs_rules.yaml,core 不认识任何领域词。

换任何系统:喂该系统的 (用例, 终态, 散文) 即自动吐出"本系统待补清单",不用人手整理。
"""
from __future__ import annotations

from typing import Any

# 终态关键字 → (owner, 泛化说明)。owner ∈ tool/env/product/defect;PASS 返回 None(不入清单)
BASE: dict[str, Any] = {
    "PASS": None,
    "FAIL": ("defect", "已检出缺陷,待开发确认修复(工具已照实报)"),
    "BLOCKED": ("product", "规则/口径未定义,需产品拍板后才能验收"),
    "NEEDS_TRIGGER": ("env", "需异步事件触发源 + 等待口径(触发后 eventmap 自动学等多久/断哪表)"),
    "PENDING·接口": ("tool", "配端点或录一次动作报文即可建模执行"),
    "PENDING·写入": ("tool", "配写端点 + 断言即可建模执行"),
    "PENDING·UI": ("tool", "page_probe 自探页面结构 + 三层校验即可建模"),
}
OWNER_TITLE = {
    "tool": "🔧 工具侧(补路由/建模/录报文即可,不缺外部东西)",
    "env": "🔑 环境侧(需你提供:账号/触发口径/场景数据/文件)",
    "product": "📋 产品侧(规则/口径未定义,需拍板)",
    "defect": "🐞 已检出缺陷(开发确认修)",
}

# 就绪门禁(core/readiness)机器判定的阻塞原因 → (owner, need)。
# 机器判定比"写关键词乐观猜"可信:仅用它锐化泛化的 tool 归属(见 disposition.classify_disposition)。
BLOCKED_OWNER: dict[str, Any] = {
    "rule": ("product", "规则/口径未定义,需产品拍板后才能验收"),
    "role": ("env", "当前账号够不到该接口,需对应角色账号解锁"),
    "action-body": ("tool", "接口从未在流量里出现,需先录一次真实动作报文后建模(触发需对应账号/场景可达)"),
}


def owner_for_blocked(blocked_by: list[str] | None):
    """按就绪门禁阻塞原因取 (owner, need);多原因取第一个已知的。无则 None。"""
    for b in (blocked_by or []):
        if b in BLOCKED_OWNER:
            return BLOCKED_OWNER[b]
    return None


def _load_refine() -> list[dict]:
    """业务细化规则(workspace):[{match:[关键词...], owner, need}]。core 无则空。"""
    try:
        import yaml
        from core.workspace import config_dir
        p = config_dir() / "env_needs_rules.yaml"
        if p.exists():
            return yaml.safe_load(p.read_text(encoding="utf-8")) or []
    except Exception:  # noqa: BLE001
        pass
    return []


def classify_need(state_label: str, prose: str, refine: list[dict] | None = None):
    """(终态标签, 用例散文) → (owner, need) 或 None(已通过)。"""
    key = next((k for k in BASE if k in (state_label or "")), None)
    base = BASE.get(key) if key else ("tool", "待建模")
    if base is None:
        return None
    owner, need = base
    # 细化只"锐化"泛化的 tool(待建模)归属 → 更具体的 env/product;
    # 绝不覆盖 product(口径)/defect(缺陷)/env(异步触发)这些已定归属,免误判。
    if owner == "tool":
        for rule in (refine or []):
            if any(kw in prose for kw in (rule.get("match") or [])):
                owner, need = rule.get("owner", owner), rule.get("need", need)
                break
    return owner, need


def build_env_needs(rows: list[tuple[str, str, str, str]], refine: list[dict] | None = None) -> dict[str, list]:
    """rows: [(case_id, name, state_label, prose)] → {owner: [(case_id, name, need)]}。"""
    refine = refine if refine is not None else _load_refine()
    groups: dict[str, list] = {}
    for cid, name, state, prose in rows:
        r = classify_need(state, prose, refine)
        if r is None:
            continue
        owner, need = r
        groups.setdefault(owner, []).append((cid, name, need))
    return groups


def render_md(groups: dict[str, list], *, title: str = "环境待补清单(自动生成)") -> str:
    out = [f"# {title}", "", "> 每条没通过的用例按『该谁补』归类;本清单由工具自动产出,换系统重跑即更新。", ""]
    total = sum(len(v) for v in groups.values())
    out.append("## 汇总")
    for owner in ("tool", "env", "product", "defect"):
        if groups.get(owner):
            out.append(f"- {OWNER_TITLE[owner]}:{len(groups[owner])} 条")
    out.append(f"- 合计待处理:{total} 条\n")
    for owner in ("env", "product", "tool", "defect"):
        items = groups.get(owner) or []
        if not items:
            continue
        out += [f"## {OWNER_TITLE[owner]}（{len(items)}）", "", "| 用例 | 缺什么 / 怎么补 |", "|---|---|"]
        # 按 need 聚合更易读
        for cid, name, need in sorted(items, key=lambda x: x[0]):
            out.append(f"| {cid} {name[:28]} | {need} |")
        out.append("")
    return "\n".join(out)
