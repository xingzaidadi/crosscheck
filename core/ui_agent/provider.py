"""Optional workspace-provided planner without making an LLM mandatory."""
from __future__ import annotations

from core.registry import get


SAFE_PROVIDER_ACTIONS = {
    "click", "text", "number", "textarea", "select", "search_select", "date",
    "press", "hover", "open_first_record", "go_to_page", "observe",
}

SAFE_ACTION_FIELDS = {
    "action", "text", "label", "value", "purpose", "page", "key", "target",
    "confidence", "reason", "exploration",
}


def invoke_planner(provider, **context):
    """Invoke a workspace planner using either a function or ``plan`` object.

    The adapter deliberately has no model dependency. A workspace may connect
    an LLM, a local model, or a deterministic domain planner, while the core
    still validates the returned action before execution.
    """
    if provider is None:
        return None
    if callable(provider):
        return provider(**context)
    plan = getattr(provider, "plan", None)
    if callable(plan):
        return plan(**context)
    return None


def normalize_proposal(proposal):
    """Normalize a model/plugin response without trusting arbitrary payloads."""
    if not isinstance(proposal, dict):
        return {}
    action = proposal.get("action")
    if isinstance(action, str):
        action = {"action": action}
    if not isinstance(action, dict):
        return {}
    if any(key not in SAFE_ACTION_FIELDS for key in action):
        return {}
    return {
        "action": dict(action),
        "confidence": max(0.0, min(1.0, float(proposal.get("confidence") or 0.0))),
        "reason": str(proposal.get("reason") or ""),
    }


def planner_provider():
    """Return a workspace plugin planner, if one is registered.

    A plugin may call ``registry.register('ui_planner', 'default', fn)``.
    The function is intentionally optional: deterministic planning remains the
    offline and safety-preserving fallback.
    """
    return get("ui_planner", "default")
