"""Validate explicit, bounded write-test permissions.

The browser runner must never infer a cleanup scope from prose.  A write
scope is a small declarative contract carried in the run report and attached
to every mutating case.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class WritePolicy:
    environment: str
    marker: str
    allowed_actions: tuple[str, ...]
    cleanup: str
    actor: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_write_scope(value: str | dict[str, Any] | None) -> WritePolicy | None:
    if isinstance(value, dict):
        data = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        data: dict[str, Any] = {}
        for key, raw in re.findall(r"(environment|env|marker|actions?|cleanup|actor)\s*[:=]\s*([^;]+)", text, re.I):
            data["environment" if key.lower() in {"environment", "env"} else
                 "allowed_actions" if key.lower().startswith("action") else key.lower()] = raw.strip()
        if not data:
            data = {"environment": text, "marker": "", "allowed_actions": [], "cleanup": ""}
    actions = data.get("allowed_actions", data.get("actions", []))
    if isinstance(actions, str):
        actions = tuple(item.strip() for item in re.split(r"[,，/|]", actions) if item.strip())
    else:
        actions = tuple(str(item).strip() for item in actions or [] if str(item).strip())
    return WritePolicy(environment=str(data.get("environment") or "").strip(),
                       marker=str(data.get("marker") or "").strip(),
                       allowed_actions=actions,
                       cleanup=str(data.get("cleanup") or "").strip(),
                       actor=str(data.get("actor") or "").strip())


def validate_write_policy(value: str | dict[str, Any] | None) -> list[dict[str, str]]:
    policy = parse_write_scope(value)
    if policy is None:
        return [{"field": "write_scope", "message": "写操作必须提供环境、数据标记、允许动作和清理策略"}]
    errors = []
    if not policy.environment:
        errors.append({"field": "environment", "message": "必须明确非生产测试环境"})
    if not policy.marker or len(policy.marker) < 3:
        errors.append({"field": "marker", "message": "必须提供至少 3 个字符的测试数据标记"})
    if not policy.allowed_actions:
        errors.append({"field": "allowed_actions", "message": "必须列出允许的写操作"})
    if not policy.cleanup:
        errors.append({"field": "cleanup", "message": "必须提供清理、撤回或补偿策略"})
    if re.search(r"prod|生产|线上", policy.environment, re.I):
        errors.append({"field": "environment", "message": "禁止在生产环境执行 UI 写测试"})
    return errors
