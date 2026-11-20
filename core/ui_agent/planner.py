"""Observation-driven planner for safe autonomous UI exploration."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from core.ui_agent.risk_policy import WRITE_TERMS
from core.ui_agent.semantic import equivalent
from core.ui_agent.provider import SAFE_PROVIDER_ACTIONS, invoke_planner, normalize_proposal


STOP_WORDS = {
    "点击", "打开", "进入", "切换", "查看", "找到", "选择", "页面", "菜单", "模块", "列表",
    "确认", "验证", "检查", "显示", "详情", "第一条", "一条", "click", "open", "view",
}
NAV_ROLES = {"button", "link", "tab", "menuitem", "treeitem"}


def _tokens(value: str) -> list[str]:
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", " ", str(value or "")).strip().lower()
    parts = [part for part in text.split() if part and part not in STOP_WORDS]
    expanded: list[str] = []
    for part in parts:
        expanded.append(part)
        if len(part) >= 4 and re.search(r"[\u4e00-\u9fff]", part):
            expanded.extend(part[index:index + 2] for index in range(len(part) - 1))
    return list(dict.fromkeys(expanded))


def _control_name(control: dict[str, Any]) -> str:
    return str(control.get("text") or control.get("label") or control.get("name") or "").strip()


def _is_dangerous(control: dict[str, Any]) -> bool:
    value = _control_name(control).lower()
    return any(term.lower() in value for term in WRITE_TERMS)


def _score_control(control: dict[str, Any], target: str, instruction: str) -> float:
    name = _control_name(control)
    if not name or control.get("disabled") or _is_dangerous(control):
        return -1.0
    target_lower = target.lower()
    name_lower = name.lower()
    if equivalent(name, target):
        return 100.0
    if target_lower and (target_lower in name_lower or name_lower in target_lower):
        return 70.0
    target_tokens = set(_tokens(target))
    instruction_tokens = set(_tokens(instruction))
    name_tokens = set(_tokens(name))
    overlap = len(name_tokens & target_tokens)
    context_overlap = len(name_tokens & instruction_tokens)
    role = str(control.get("role") or control.get("tag") or "").lower()
    role_bonus = 4 if role in NAV_ROLES or role in {"a", "button"} else 0
    return overlap * 20 + context_overlap * 3 + role_bonus


def action_visible(action: dict[str, Any], observation: dict[str, Any]) -> bool:
    kind = str(action.get("action") or "")
    if kind == "reach":
        target = str(action.get("target") or "")
        body = str(observation.get("body_text") or "")
        return bool(target and (target in body or any(
            _score_control(item, target, target) >= 70 for item in observation.get("controls") or []
        )))
    if kind in {"observe", "open_first_record", "select_first_row", "prepare_filter"}:
        return kind != "open_first_record" or bool(observation.get("tables") or observation.get("rows"))
    if kind in {"text", "number", "textarea", "select", "search_select", "date"}:
        target = str(action.get("label") or "")
        if not target:
            return True
        return any(
            target in str(field.get("label") or "") or target in str(observation.get("body_text") or "")
            for field in observation.get("fields") or [{}]
        )
    if kind == "search_value":
        return bool(observation.get("fields"))
    if kind == "switch_tabs":
        labels = [str(item) for item in action.get("labels") or []]
        names = {_control_name(item) for item in observation.get("controls") or []}
        return not labels or any(label in names for label in labels)
    target = str(action.get("text") or action.get("label") or action.get("name") or "")
    if not target:
        return True
    return any(_score_control(item, target, target) >= 70 for item in observation.get("controls") or [])


def _is_detail_goal(action: dict[str, Any]) -> bool:
    value = " ".join(str(item) for item in action.values())
    return any(term in value for term in ("详情页", "详情页面", "进入详情", "查看详情", "open_first_record"))


@dataclass
class PlannerState:
    pending_actions: list[dict[str, Any]]
    attempted_gateways: set[str] = field(default_factory=set)
    completed_actions: list[dict[str, Any]] = field(default_factory=list)
    stagnant_rounds: int = 0
    last_fingerprint: str = ""
    seen_fingerprints: set[str] = field(default_factory=set)


@dataclass
class PlannerDecision:
    kind: str
    action: dict[str, Any] | None
    reason: str
    confidence: float
    desired_action: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ObservationPlanner:
    def __init__(self, instruction: str, actions: list[dict[str, Any]], resolver=None):
        self.instruction = instruction
        self.resolver = resolver
        self.state = PlannerState(pending_actions=[dict(item) for item in actions])

    def update_observation(self, observation: dict[str, Any]) -> None:
        fingerprint = "|".join([
            str(observation.get("url") or ""),
            str(observation.get("body_text") or "")[:1000],
            ",".join(_control_name(item) for item in observation.get("controls") or []),
        ])
        if fingerprint == self.state.last_fingerprint:
            self.state.stagnant_rounds += 1
        else:
            self.state.stagnant_rounds = 0
            self.state.last_fingerprint = fingerprint
        self.state.seen_fingerprints.add(fingerprint)

    def decide(self, observation: dict[str, Any], *, assertions_passed: bool = False) -> PlannerDecision:
        self.update_observation(observation)
        if assertions_passed and not self.state.pending_actions:
            return PlannerDecision("complete", None, "all goals and assertions are satisfied", 1.0)
        if self.state.pending_actions and all(
            str(item.get("action") or "") == "observe" for item in self.state.pending_actions
        ):
            desired = self.state.pending_actions[0]
            return PlannerDecision(
                "verify",
                {"action": "observe", "target": desired.get("target", "current_page")},
                "the requested check only needs the current page observation",
                .95,
                desired_action=desired,
            )
        if self.state.stagnant_rounds >= 3:
            return PlannerDecision("blocked", None, "page state did not change after bounded exploration", 1.0)
        if self.state.pending_actions:
            desired = self.state.pending_actions[0]
            if desired.get("action") == "reach" and action_visible(desired, observation):
                target = str(desired.get("target") or "")
                if target in str(observation.get("body_text") or ""):
                    return PlannerDecision("execute", {"action": "observe", "target": target},
                                           "requested goal is observable on the current page", .95,
                                           desired_action=desired)
                return PlannerDecision("execute", {"action": "click", "text": target},
                                       "requested goal is a visible control", .9,
                                       desired_action=desired)
            if desired.get("action") == "search_value" and observation.get("fields"):
                field = next((item for item in observation.get("fields") or []
                              if not item.get("disabled") and not item.get("readonly")), None)
                if field:
                    label = field.get("label") or field.get("name") or ""
                    return PlannerDecision(
                        "execute",
                        {"action": "text", "label": label,
                         "value": desired.get("value"), "purpose": "query"},
                        "using the first editable query field for the requested value", .78,
                        desired_action=desired,
                    )
            if action_visible(desired, observation):
                if desired.get("action") == "click" and str(desired.get("text") or "") in {"详情", "查看详情", "明细"}:
                    return PlannerDecision("execute", desired, "detail navigation control is visible", .95,
                                           desired_action=desired)
                return PlannerDecision("execute", desired, "desired action is visible in current observation", .95,
                                       desired_action=desired)
            gateway = self._gateway_for(desired, observation)
            if gateway:
                return PlannerDecision(
                    "explore", {"action": "click", "text": gateway["name"], "exploration": True},
                    "target is hidden; opening the best safe semantic gateway", gateway["confidence"],
                    desired_action=desired,
                )
            resolved = self._resolve_with_provider(desired, observation)
            if resolved:
                return resolved
            if desired.get("action") == "open_first_record":
                fallback = self._instruction_gateway(observation)
                if fallback:
                    return PlannerDecision(
                        "explore", {"action": "click", "text": fallback["name"], "exploration": True},
                        "record container is absent; using the explicit instruction target", fallback["confidence"],
                        desired_action=desired,
                    )
            if observation.get("tables") and self._requests_first_record(desired):
                return PlannerDecision("execute", {"action": "open_first_record"},
                                       "instruction requests a record and a table is available", .85,
                                       desired_action=desired)
            return PlannerDecision("blocked", None, "no safe semantic path to the pending action", .9,
                                   desired_action=desired)
        if assertions_passed:
            return PlannerDecision("complete", None, "assertions are satisfied", 1.0)
        return PlannerDecision("verify", None, "no pending actions; evaluate assertions", 1.0)

    def _resolve_with_provider(self, desired: dict[str, Any], observation: dict[str, Any]) -> PlannerDecision | None:
        if self.resolver is None:
            return None
        try:
            proposal = normalize_proposal(invoke_planner(self.resolver,
                instruction=self.instruction,
                desired_action=dict(desired),
                observation=dict(observation),
                attempted_gateways=sorted(self.state.attempted_gateways),
            ) or {})
        except Exception:
            return None
        action = proposal.get("action") if isinstance(proposal, dict) else None
        if not isinstance(action, dict) or action.get("action") not in SAFE_PROVIDER_ACTIONS:
            return None
        if not self._provider_action_is_safe(action, observation):
            return None
        return PlannerDecision(
            "explore", action,
            str(proposal.get("reason") or "semantic planner selected a safe observable action"),
            float(proposal.get("confidence") or .65), desired_action=desired,
        )

    def _provider_action_is_safe(self, action: dict[str, Any], observation: dict[str, Any]) -> bool:
        kind = str(action.get("action") or "")
        if action.get("selector") or action.get("xpath") or action.get("javascript"):
            return False
        if kind == "observe":
            return True
        if kind == "open_first_record":
            return bool(observation.get("tables") or observation.get("rows"))
        if kind == "go_to_page":
            target = str(action.get("page") or "")
            return bool(target and any(target in _control_name(item) for item in observation.get("controls") or []))
        if kind == "press":
            return str(action.get("key") or "").lower() in {"enter", "escape", "tab", "arrowdown", "arrowup"}
        if kind in {"text", "number", "textarea", "select", "search_select", "date"}:
            label = str(action.get("label") or "")
            return bool(label and any(
                label in str(field.get("label") or "")
                or label in str(field.get("name") or "")
                for field in observation.get("fields") or []
            ))
        target = str(action.get("text") or action.get("label") or "")
        if not target:
            return False
        visible_names = {_control_name(item) for item in observation.get("controls") or []}
        return any(
            target == name or equivalent(target, name)
            for name in visible_names
        ) and target not in self.state.attempted_gateways

    def mark_success(self, decision: PlannerDecision) -> None:
        if decision.kind == "explore" and decision.action:
            target = str(decision.action.get("text") or decision.action.get("label") or "")
            if target:
                self.state.attempted_gateways.add(target)
            desired = decision.desired_action or {}
            gateway_text = str(decision.action.get("text") or "")
            if desired.get("action") == "open_first_record" and any(
                term in gateway_text for term in ("详情", "记录", "明细", "detail", "record")
            ) and self.state.pending_actions:
                self.state.completed_actions.append(self.state.pending_actions.pop(0))
            return
        desired = decision.desired_action
        if desired and self.state.pending_actions and desired == self.state.pending_actions[0]:
            self.state.completed_actions.append(self.state.pending_actions.pop(0))

    def mark_blocked(self, decision: PlannerDecision, observation: dict[str, Any]) -> bool:
        """Drop an already-observed no-op and allow the next goal to run.

        A navigation label may already be rendered as a heading while the
        corresponding button is the only executable control.  Treating that
        goal as completed avoids repeatedly blocking on a textual target.
        """
        desired = decision.desired_action or {}
        if desired.get("action") == "reach":
            target = str(desired.get("target") or "")
            if target and target in str(observation.get("body_text") or ""):
                if self.state.pending_actions and desired == self.state.pending_actions[0]:
                    self.state.completed_actions.append(self.state.pending_actions.pop(0))
                    return True
        return False

    def _gateway_for(self, desired: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any] | None:
        target = str(desired.get("text") or desired.get("label") or desired.get("name")
                     or desired.get("target") or "")
        ranked: list[tuple[float, str]] = []
        for control in observation.get("controls") or []:
            name = _control_name(control)
            if not name or name in self.state.attempted_gateways:
                continue
            score = _score_control(control, target, self.instruction)
            if score >= 7:
                ranked.append((score, name))
        if not ranked:
            return self._safe_navigation_gateway(observation)
        score, name = max(ranked, key=lambda item: (item[0], -len(item[1])))
        return {"name": name, "confidence": min(.9, .45 + score / 100)}

    def _safe_navigation_gateway(self, observation: dict[str, Any]) -> dict[str, Any] | None:
        """Choose one bounded, non-mutating navigation step when the target is hidden."""
        ranked: list[tuple[float, str]] = []
        for control in observation.get("controls") or []:
            name = _control_name(control)
            role = str(control.get("role") or control.get("tag") or "").lower()
            if not name or name in self.state.attempted_gateways or _is_dangerous(control):
                continue
            if role not in NAV_ROLES and role not in {"a", "button"}:
                continue
            score = 0.0
            if control.get("href"):
                score += 2
            if role in {"link", "button", "tab", "menuitem"}:
                score += 3
            score += min(4, len(set(_tokens(name)) & set(_tokens(self.instruction))))
            if score >= 4:
                ranked.append((score, name))
        if not ranked:
            return None
        score, name = max(ranked, key=lambda item: (item[0], -len(item[1])))
        return {"name": name, "confidence": min(.72, .42 + score / 20)}

    def _instruction_gateway(self, observation: dict[str, Any]) -> dict[str, Any] | None:
        ranked = []
        for control in observation.get("controls") or []:
            name = _control_name(control)
            if not name or name in self.state.attempted_gateways or _is_dangerous(control):
                continue
            if name in self.instruction:
                ranked.append((len(name), name))
        if not ranked:
            return None
        _, name = max(ranked)
        return {"name": name, "confidence": .8}

    @staticmethod
    def _requests_first_record(action: dict[str, Any]) -> bool:
        value = " ".join(str(item) for item in action.values())
        return any(term in value for term in ("第一条", "首条", "第一行", "详情"))
