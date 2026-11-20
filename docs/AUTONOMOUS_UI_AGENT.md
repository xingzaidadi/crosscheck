# Autonomous UI Agent

Crosscheck supports a natural-language, safety-bounded UI testing path alongside the existing deterministic suite runner.

## Run

```powershell
crosscheck test https://test.example.com/orders "打开订单管理，切换到处理中，确认详情页只读"

# URL 也可以直接放进自然语言句子
crosscheck test "帮我测试 https://test.example.com/orders：查询订单1001并确认状态为待处理"

# Advanced equivalent:
crosscheck agent-test --url https://test.example.com/orders `
  --instruction "打开订单管理，切换到处理中，确认详情页只读" `
  --workspace workspace
```

No case file, canonical suite, selector configuration, or Playwright code is required. Existing profiles and sessions are discovered and reused. First-time SSO, MFA, and CAPTCHA still require a human login.

`crosscheck test` is the default product entrypoint. It starts an immediate
exploratory run without requiring a case file. With `--cases`, it runs the
recommended case-driven mode. If a profile does not exist,
the Agent still starts from the URL. When a login page is detected, run headed
once, complete SSO/MFA/CAPTCHA in the opened browser, and the discovered session
is saved for reuse. The Agent only asks for clarification when an expected result
cannot be converted into an observable assertion or a write scope is missing.

The same entrypoint accepts `--session`, `--role`, `--risk-policy`,
`--allow-write`, `--write-scope`, `--run-id`, and `--save-regression` for
advanced runs. A run is not saved as a regression asset by default; use
`--save-regression` when the successful exploration should be reused. These
are execution controls, not UI automation configuration: users do not need to
provide selectors, page models, bindings, or Playwright code.

## Four phases

1. **Natural-language execution**: converts the instruction into a temporary action and oracle plan.
2. **Autonomous exploration and recovery**: observes the page, uses semantic locators, retries alternate strategies, and records recovery evidence.
3. **Assertion and optional hardening**: generates evidence-bound assertions. Only runs explicitly started with `--save-regression` are promoted to `provisional` regression assets. Write-risk assets remain review-required.
4. **Maturity acceptance**: `scripts/maturity_acceptance.py` scores real execution samples and only passes at 90+ with all safety and phase gates satisfied.

## Exploration loop

The Agent does not only replay a fixed list. Each round observes the current URL, visible controls, headings, fields, tables, rows, and page text; the observation planner then chooses one of `execute`, `explore`, `verify`, `complete`, or `blocked`. If the requested target is not visible, it selects a safe semantic gateway, acts, observes the changed page, and replans. The bounded loop records every decision, confidence, recovery strategy, and evidence artifact.

The planner can optionally be extended by a workspace provider or model. The
provider returns one JSON action at a time; Crosscheck validates its action
against the observed page, the selector-free allowlist, and the active risk
policy before execution. No model or provider configuration is required for
the default deterministic fallback.

This specifically addresses the former gap where observation happened only before a pre-generated action list. A real-browser benchmark is available:

```powershell
crosscheck ui-agent-benchmark --output artifacts/ui-agent-benchmark --repetitions 100
```

The benchmark includes nested navigation, tabs, first-record access, direct detail navigation, read-only pages, and the four-phase gates. It is a baseline, not a substitute for running the same benchmark against the user's real application.

For real-system acceptance, prepare a YAML manifest with at least 30 representative
read-only tasks and run:

```powershell
crosscheck real-ui-acceptance --manifest real-ui-scenarios.yaml `
  --output artifacts/real-ui-acceptance --workspace workspace
```

Start from `templates/real_ui_acceptance.example.yaml`; no selectors or browser
automation code belong in the manifest.

The report measures first-pass success, blocked runs, human intervention,
unsafe actions, and unresolved expectations. This separates product maturity
from synthetic benchmark performance.

Every successful result must include at least one objective UI assertion. Runs
without an executable assertion are reported as `INCONCLUSIVE`, never as
`PASSED`. A stable read-only path is fingerprinted and stored as a provisional
regression asset; later identical requests reuse the asset and fall back to
autonomous exploration when it is absent or no longer executable.

## Natural-language clarification and cross-layer evidence

Generic requests such as `帮我测试订单中心是否正常` are converted into a
reachable target plus a page-health assertion. The Agent checks that the page
loaded, contains visible content, and does not expose common server-error
messages. If a request has neither an executable action nor an observable
expected result, the run returns `NEEDS_INPUT` with structured clarification
questions instead of asking the user to write selectors or Playwright code.
Answers can be supplied with repeated `--answer` options:

```powershell
crosscheck test https://test.example.com "帮我看看这个系统" `
  --answer "测试订单中心" `
  --answer "确认列表可见并且页面只读"
```

Requests mentioning API, database, or events declare the requested layers in
the report. Browser XHR/fetch status metadata is captured as evidence and an
explicit API status such as `确认接口状态码为200` is evaluated. Database and
event layers are reported as `NEEDS_CONFIG` until a workspace connector and a
concrete oracle are supplied; they are never silently marked PASS.

## Built-in quality and regression evidence

Every autonomous run also captures a semantic page map, screenshots, DOM,
frontend console/page errors, failed requests, navigation timing, and a small
accessibility smoke audit. Requests such as `确认页面加载不超过2秒` create a
performance threshold, while requests mentioning `视觉/截图/布局` compare the
captured page against an approved baseline when one exists, or mark the image
as a review candidate when it does not. API JSON evidence is summarized with
secret fields redacted.

Broad requests produce safe read-only scenario suggestions (happy path, empty
query, not found, reset filters, and role variants). The report includes the
active role, data strategy, connector readiness, scenario suggestions, and
recent run history. These are evidence and suggestions, not automatic PASS;
external DB/MQ/event checks remain connector- and oracle-gated.

## Safety

- Navigation, tabs, pagination, search, filtering, and detail viewing are autonomous.
- Business data edits require `--risk-policy authorized_write --allow-write --write-scope "..."`.
- Destructive actions remain blocked even under generic write authorization.
- Production access and credentials remain governed by the existing workspace and profile controls.

## MCP

`crosscheck_task_create` accepts `operation: agent_test` with `url` and `instruction`; a canonical suite is not required for this operation. Successful exploratory paths can still be hardened into deterministic assets for later regression.
