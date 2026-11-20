"""Safety policy for autonomous browser actions."""
from __future__ import annotations

from dataclasses import dataclass


WRITE_TERMS = (
    "保存", "提交", "删除", "审批", "驳回", "上传", "导入", "发布", "作废", "撤回",
    "save", "submit", "delete", "approve", "reject", "upload", "import", "publish",
)
READ_INPUT_TERMS = ("搜索", "查询", "筛选", "过滤", "search", "query", "filter")
DESTRUCTIVE_TERMS = ("删除", "作废", "delete", "destroy", "drop")


@dataclass
class RiskDecision:
    allowed: bool
    level: str
    reason: str


def assess_action(action: dict, *, policy: str, allow_write: bool = False,
                  write_scope: str = "") -> RiskDecision:
    text = " ".join(str(value) for value in action.values()).lower()
    action_name = str(action.get("action") or "").lower()
    is_read_input = any(term in text for term in READ_INPUT_TERMS)
    is_write = (action_name in {"save", "submit", "delete", "upload"}
                or (action_name in {"fill", "text", "select"} and not is_read_input)
                or any(term in text for term in WRITE_TERMS))
    destructive = action_name == "delete" or any(term in text for term in DESTRUCTIVE_TERMS)
    if destructive:
        return RiskDecision(False, "destructive", "destructive actions require explicit external approval")
    if not is_write:
        return RiskDecision(True, "read_only", "safe autonomous action")
    if policy == "authorized_write" and allow_write and write_scope.strip():
        return RiskDecision(True, "authorized_write", "write action covered by explicit scope")
    return RiskDecision(False, "write", "write action blocked by the active risk policy")
