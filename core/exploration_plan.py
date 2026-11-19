"""Turn unresolved assertions into safe browser or information-gathering tasks."""
from __future__ import annotations

from typing import Any


def classify_assertion_gap(text: str) -> dict[str, Any]:
    value = str(text or "")
    if any(term in value for term in ("A ", "B ", "管理员", "角色", "权限", "越权", "仅见", "自己的")):
        return {
            "gap_type": "ROLE_OR_AUTH_CONTEXT",
            "required_inputs": ["role_sessions", "role_expectations"],
            "safe_to_auto_explore": False,
            "strategy": "multi_role_browser_replay",
        }
    if any(term in value for term in ("跳转", "新建页", "中间页", "页签")):
        return {
            "gap_type": "PAGE_NAVIGATION",
            "required_inputs": ["page_entry"],
            "safe_to_auto_explore": True,
            "strategy": "read_only_navigation_probe",
        }
    if any(term in value for term in ("显示", "展示", "字段", "为空", "状态", "列表", "详情")):
        return {
            "gap_type": "UI_ORACLE",
            "required_inputs": ["page_entry", "target_fields"],
            "safe_to_auto_explore": True,
            "strategy": "read_only_dom_probe",
        }
    if any(term in value for term in ("\u63d0\u4ea4", "\u4fdd\u5b58", "\u521b\u5efa", "\u53d7\u7406", "\u5ba1\u6279", "\u5220\u9664", "\u5bfc\u51fa")):
        return {
            "gap_type": "MUTATING_ACTION_OR_PERMISSION",
            "required_inputs": ["write_authorization", "cleanup_recipe", "action_asset"],
            "safe_to_auto_explore": False,
            "strategy": "reviewed_action_recording",
        }
    if any(term in value for term in ("落库", "记录", "数据库", "快照")):
        return {
            "gap_type": "DATA_ORACLE",
            "required_inputs": ["approved_db_mapping", "read_only_db_access"],
            "safe_to_auto_explore": False,
            "strategy": "db_oracle_review",
        }
    return {
        "gap_type": "BUSINESS_RULE",
        "required_inputs": ["approved_business_rule"],
        "safe_to_auto_explore": False,
        "strategy": "knowledge_question",
    }


def build_exploration_task(candidate: dict[str, Any], *, page_url: str = "", session: str = "") -> dict[str, Any]:
    classification = classify_assertion_gap(str(candidate.get("text") or ""))
    task = {
        **candidate,
        **classification,
        "page_url": page_url,
        "session": session,
        "status": "READY_TO_EXPLORE" if classification["safe_to_auto_explore"] and page_url
        else "WAITING_FOR_INPUT",
        "evidence_required": ["before_screenshot", "after_screenshot", "dom_snapshot", "replay_result"],
    }
    if classification["gap_type"] == "ROLE_OR_AUTH_CONTEXT":
        task["evidence_required"] += ["role_identity", "per_role_result"]
    return task
