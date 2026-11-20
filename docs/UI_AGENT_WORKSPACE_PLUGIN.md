# UI Agent Workspace Plugin

The natural-language entrypoint works without an LLM or selectors. For a real
system that needs domain vocabulary, add an optional planner plugin at
`workspace/plugins/ui_planner.py`:

```python
from core.registry import register

def plan(**context):
    observation = context["observation"]
    desired = context["desired_action"]
    # Return only a visible, safe gateway. The runtime validates it again.
    for control in observation.get("controls", []):
        if control.get("text") == "订单中心":
            return {"action": {"action": "click", "text": "订单中心"}, "confidence": 0.9}
    return None

register("ui_planner", "default", plan)
```

The provider may also return a safe observed form action when the field is
visible:

```python
def plan(**context):
    fields = context["observation"].get("fields", [])
    if any(field.get("label") == "订单号" for field in fields):
        return {"action": {"action": "text", "label": "订单号",
                            "value": "1001", "purpose": "query"},
                "confidence": 0.86}
    return None
```

Supported provider actions are limited to observable, selector-free actions:
navigation clicks, query fields, safe selects, pagination, keyboard navigation,
hover, first-record opening, and observation. A returned selector, XPath, or
JavaScript payload is rejected before execution. Query fields must use
`purpose: query`; writes remain subject to the active risk policy and
destructive actions remain blocked.

The same contract can wrap a model client: pass the natural-language
instruction and structured observation to the model, require a single JSON
action, and return it from `plan(**context)`. Do not execute model output
directly and do not return selectors or JavaScript.
