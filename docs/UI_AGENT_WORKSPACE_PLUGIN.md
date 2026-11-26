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

## Offline semantic matching comes first (no plugin required)

Before any plugin is consulted, the deterministic planner already resolves
synonymous wording offline: a test case that says `下单` matches a button
labelled `提交`, `新增`/`创建`/`add` collapse to one target, and so on. These
alias groups live in `core/ui_agent/semantic.py` (`ALIASES`, matched by
`equivalent`) and contain only **generic UI verbs** — never domain words. This
is why the planner stays reproducible, offline, and zero-cost by default; the
model plugin below is an **optional** second layer.

The deterministic layer handles aliases, substrings, and token overlap. It
cannot bridge *domain* synonyms it has never been told about — e.g. a case that
says `客户资料` landing on a page whose only control is `会员档案` (no shared
token, no generic alias). When the best deterministic gateway is only a **weak,
coincidental match** (confidence below `WEAK_GATEWAY_CONFIDENCE`), the planner
consults the optional provider *before* taking that weak gateway. A strong
alias/substring hit never spends a provider call. So the model fires exactly
where offline matching is genuinely unsure — not as a blind last resort, and
not when the deterministic layer already has a confident answer.


## Model-backed planner stub (optional, off by default)

The planner calls `registry.get("ui_planner", "default")`. When nothing is
registered it returns `None` and the planner falls back to deterministic
matching — so **doing nothing keeps the tool fully offline**. To opt in, add a
guarded plugin that only activates when a key is present:

```python
# workspace/plugins/ui_planner.py
import os
from core.registry import register

def _client():
    key = os.environ.get("UI_PLANNER_API_KEY")  # explicit opt-in: no key, no model
    if not key:
        return None
    # return your model client here (Claude / OpenAI / local); core ships none.
    ...

def plan(**context):
    client = _client()
    if client is None:
        return None  # deterministic planner stays in charge
    observation = context["observation"]
    desired = context["desired_action"]
    controls = [c.get("name") for c in observation.get("controls", []) if c.get("name")]
    # Ask the model for ONE action, choosing only from visible control names.
    # Require a strict JSON shape; never let it emit selectors/xpath/javascript.
    raw = client.choose_action(
        instruction=context["instruction"],
        desired=desired,
        visible_controls=controls,
    )  # e.g. {"action": {"action": "click", "text": "订单中心"},
       #       "confidence": 0.8, "reason": "closest visible gateway"}
    return raw  # runtime re-validates via normalize_proposal + _provider_action_is_safe

register("ui_planner", "default", plan)
```

The runtime validates the returned action again before execution: unknown
fields, selectors, XPath, or JavaScript payloads are rejected
(`provider.normalize_proposal`, `planner._provider_action_is_safe`), and write
actions still pass through the active risk policy. The model's `reason` and
`confidence` are recorded in `planner-decisions.json` alongside the
deterministic candidate scores, so every "why this control" decision is
auditable after the run.

## End-to-end proof (real browser + real model)

A worked example lives at `workspace/demo/admin.html`: a page whose only
navigation controls are `会员档案` / `交易流水`, driven by an instruction that
says `打开客户资料` (domain synonyms with **zero shared token**). The planner is
driven through the real entrypoint:

```bash
# real chromium (Python with playwright installed) + the plugin above
UI_PLANNER_LLM=1 python scripts/agent_test.py \
  --url "file:///.../workspace/demo/admin.html" \
  --instruction '打开客户资料，确认页面出现文本“数据加载成功”' \
  --no-session-refresh
```

Controlled result, same page and controls:

| provider (`UI_PLANNER_LLM`) | outcome | why |
| --- | --- | --- |
| **off** | `BLOCKED` at step 1 | deterministic alone cannot bridge `客户资料`→`会员档案` |
| **on** | `PASSED` | provider selects `会员档案`, navigation retires, assertion holds |

The offline regression `tests/test_ui_agent_provider_bridge.py` locks the same
wiring with a stub provider (no network), so the behaviour is reproducible in
CI without a live model.

