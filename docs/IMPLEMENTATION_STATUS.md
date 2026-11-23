# Implementation Status

This status is the implementation-side companion to the design plans. A passing offline contract test is not external business acceptance.

> Last updated: 2026-11-23 (tracks `00fa8ec`, 2026-11-20).
>
> Overall maturity: **M2.5 — controlled repeatable execution, transitioning toward a production-grade regression platform.** Cross-layer UI/API/DB execution, deterministic replay, evidence gates and asset lifecycle are strong; the open fronts are external multi-system acceptance, the business Oracle model, and wiring the global circuit breaker into the execution loop. See `AI测试工具产品演进方案.md` for the scored breakdown (~66/100).

| Area | Status | Verification level | Notes |
|---|---|---|---|
| Canonical suite schema/compiler | Implemented | contract | Ready cases require approval and content hash. |
| Failure taxonomy | Implemented | contract | `core/failure_class.py` maps legacy verdicts to documented classes. |
| Run event fact source | Implemented | contract/local_e2e | Runs can emit append-only `events.jsonl`; summary remains JSON. |
| Empty evidence gate | Implemented | contract/local_e2e | Empty UI/API agreement requires explicit allowance. |
| Cleanup safety | Implemented | contract/local_e2e | Registry and escaped LIKE markers are covered. |
| Local UI/API/DB demo | Implemented | local_e2e | Proves only the local integration path. |
| External acceptance | Not complete | external_ready | Strict gate now requires 3 unrelated systems, at least 20 cases per system, <=10% inconclusive, 5 soak runs, and hash-bound reports; real evidence is still required. |
| Strict external evidence integrity | Implemented | external_ready | `scripts/external_acceptance.py` now requires external_pass reports, all cases passed, and SHA-256-bound report files; no real manifest is present in this workspace. |
| Single real page 100% soak | Implemented for ebuy-demand UI pilot | external_pass | `workspace/reports/ebuy-demand-ui-acceptance/soak-final-5-summary.json` records 5 consecutive real-browser runs of TC115/TC116/TC122, each `PASS:3`; full-suite expansion remains gated by canonical readiness. |
| UI gap audit | Implemented | contract/workspace | `crosscheck ui-gap-audit` produces one current readiness, binding-candidate and next-action report instead of relying on conversational rediscovery. |
| UI binding review queue | Implemented | contract | Replay-proven assets enter an explicit review queue and cannot become human_verified without replay evidence and a named reviewer. |
| UI write policy | Implemented | contract | Mutating UI runs require an explicit non-production environment, data marker, allowed actions and cleanup/compensation strategy. |
| Versioned UI application model | Implemented | contract | `ui-onboard` creates validated page/route/role/selector/wait/frame/dialog/mask models without embedding site rules in core. |
| Readiness remediation queue | Implemented | contract | UI gaps are converted to stable business, exploration, binding, oracle or fixture tasks in `ui-gap-audit`. |
| Binding activation lifecycle | Implemented | contract | Assets use replay and named human review before `active`; only active/healthy evidence-backed assets are executable. |
| UI fixture lifecycle | Implemented | contract | Declarative local fixtures have marker validation, a run ledger, bounded cleanup and residue reporting. |
| Business arsenal stages | In progress | contract | Declarative capability packs, plan execution and compensation primitives are available; real business packs still require system-specific bindings. |
| Local requirement capability pack | Implemented | local_e2e | `core/mock_requirement.py` provides create/find/submit/approve/verify/cancel with SQLite evidence and compensation; it is a local G3 baseline, not external acceptance. |
| Local G3 soak artifact | Implemented | local_e2e | `crosscheck mock-requirement` runs the requirement lifecycle repeatedly and emits a G3 artifact. |
| Local Case v2 requirement runner | Implemented | local_e2e | `core/local_case_runner.py` executes a v2 action, evaluates API/DB oracles and aggregates required layer results against the local capability pack. |
| Local G4 requirement→strategy chain | Implemented | local_e2e | `crosscheck mock-g4` validates requirement outputs into `strategy.publish`, lineage, cross-object oracle, compensation and residue. |
| Local G5 delivery chain | Implemented | local_e2e | `crosscheck mock-g5` validates sourcing.publish → contract.sign → order.create with cross-object lineage, idempotent local storage, compensation and zero residue. |
| Local G5 acceptance matrix | Implemented | local_e2e | `crosscheck mock-g5-acceptance` runs repeated soak, injected order failure recovery, idempotency and residue checks. |
| Unified local delivery acceptance | Implemented | local_e2e | `crosscheck local-delivery-acceptance --output ...` emits one hashed artifact covering G0-G5, G4 lineage and G5 soak/fault/idempotency evidence. |
| Fault-injection harness | Implemented | contract | `core/soak.py` provides explicit fault scenarios; recovery remains a supplied capability-pack behavior. |
| Acceptance manifest integrity | Implemented | contract | Manifest hash and required-case integrity are checked by `core/manifest.py` and `feature-gate`. |
| Case quality auditor | Implemented | contract | `core/case_auditor.py` detects schema, role, source, open-question, ambiguity, precondition, oracle and duplicate gaps. |
| Unified G0/G1/G2/G-A/G-L checks | Implemented | contract | `core/gates.py` provides a unified evaluator; external business facts and real layer evidence remain inputs, not auto-created PASS. |
| Capability registry safety gate | Implemented | contract | `crosscheck arsenal` validates evidence, execution bindings, duplicate refs and compensation for mutating capabilities. |
| Capability health, object lease, dependency and compensation plan primitives | Implemented | contract | `core/arsenal.py` now includes plan execution with deterministic failure compensation. |
| Recursive dependency ordering and conflict checks | Implemented | contract | Dependency closure is topologically ordered, cycles are rejected, and conflicting locks/effects stop planning. |
| Transactional run registry and recovery checkpoint | Implemented | contract | `core/run_registry.py` persists runs, objects, leases, steps, unknown states and audit events in SQLite. |
| Unified case + arsenal master design | Implemented | design_only | `docs/archive/plans/CASE_ARSENAL_MASTER_PLAN.md` is the archived design baseline; implementation must still be checked against its gates. |
| UI/API/DB layered result model (`required/optional/deferred`, `INCONCLUSIVE`) | In progress | contract/local_e2e | Independent `LayerResult` aggregation is attached by `run_batch.finalize_result`; required/optional/deferred policy is supported, while native adapter subplans still require real case bindings. |
| UI-first → API → DB → visual rollout | Not complete | design_only | The phased route is documented; only local UI/API/DB demo coverage exists, not the staged external business rollout. |
| AI UI operation assetization | In progress | contract/local_e2e | `ui-run` now emits reviewable action/oracle binding candidates; high-confidence read-only cases are eligible for Pilot, while formal promotion still requires replay evidence and human review. |
| Case v2 executable contract | In progress | contract | `core/case_v2.py` validates/migrates v2 and projects v2 cases into the current executor; native v2 adapter bindings remain. |
| Case v2 oracle evaluation | Implemented | contract/local_e2e | Nested-path deterministic oracle operators are evaluated in `run_batch.finalize_result` when v2 evidence is present. |
| Case v2 wait/poll | Implemented | contract/local_e2e | `wait.until/timeout_s/interval_s` now polls the evidence supplier and records timeout/until status. |
| Run registry pipeline integration | Implemented | contract/local_e2e | `core/pipeline_runner.py` can create/update run and step records when a `RunRegistry` is provided. |
| Unknown-state execution handling | Implemented | contract/local_e2e | Executor exceptions are recorded as `unknown` steps and stop the pipeline instead of being blindly retried. |
| 100% per-feature self-test gate | In progress | contract | Frozen feature manifest evaluation is implemented in `core/feature_gate.py` and exposed by `crosscheck feature-gate`; soak/fault evidence must be supplied per feature. |
| UI login/session automation | Implemented | local_e2e/external_ready | URL-matched profiles validate and reuse sessions by default; expired sessions enter credential/manual refresh, with `--no-session-refresh` as the explicit opt-out. |
| UI action and oracle expansion | Implemented for supported semantics | contract/external_pass | Added prose extraction for text/select/date actions, iframe/frame actions, keyboard/wait/scroll controls, filter/status-group oracles, and preserved `INCONCLUSIVE` for unresolved evidence. |
| Natural-language task planning and clarification | Implemented for supported semantics | contract/local_e2e | Generic health goals become observable page-health checks; ambiguous requests return structured clarification questions and can be resumed with repeated `--answer` values. |
| Dynamic safe semantic exploration | Implemented for supported semantics | contract/local_e2e | The observation planner can select bounded non-mutating navigation gateways when requested targets are hidden, then re-observe and re-plan. |
| Cross-layer evidence status | Implemented for browser/API observation; connector-gated for DB/events | contract/local_e2e | Browser XHR/fetch metadata and explicit API status oracles are reported; DB/event requests remain `NEEDS_CONFIG` without workspace connectors and concrete oracles. |
| Natural-language scenario generation and role/data strategy | Implemented for supported semantics | contract | Broad requests generate safe read-only scenario suggestions; plans record role matrix and marker/cleanup strategy for mutating work. |
| Semantic page map and dynamic navigation | Implemented for supported semantics | local_e2e | Every run stores a normalized page map and the planner can select bounded safe navigation gateways when targets are hidden. |
| Frontend quality and accessibility smoke evidence | Implemented | local_e2e | Console/page errors, failed requests, navigation timing, and unnamed controls/fields/images/heading gaps are captured per run. |
| API payload evidence and field assertions | Implemented for supported semantics | local_e2e | JSON response summaries are secret-redacted and explicit API field assertions are evaluated without treating unobserved values as PASS. |
| Visual candidate and approved-baseline comparison | Implemented for supported semantics | local_e2e | Visual requests compare against approved baselines or produce review candidates; no baseline is silently accepted. |
| Agent run history and audit context | Implemented | contract/local_e2e | Reports include recent run history, role, risk, data strategy, planner decisions, recovery events, and connector readiness. |
| Prototype/visual comparison | In progress | contract | Pixel/structural comparison, baseline storage/approval and `crosscheck visual-compare` / `visual-baseline` are implemented; browser capture orchestration remains. |
| Unified product quality gate | Implemented | contract/workspace | `crosscheck quality-gate` combines maturity, preparation, Oracle, run evidence and approved-asset health with configurable CI thresholds. |
| Business-domain capability pack and coverage | Implemented | contract/workspace | `workspace/config/capabilities.yaml` provides a validated ebuy-demand pack; `crosscheck domain-capability` classifies precondition actions and reports coverage/gaps, which the quality gate enforces. |
| Global circuit breaker (deterministic stop) | Core implemented | contract | `core/circuit_breaker.py` counts consecutive same-class failures per `(case_id, failure_class)`, trips at a configurable threshold (default 3, env 2) into a hash-bound `BLOCKED_NEEDS_HUMAN` handoff packet; terminal classes (`SPEC_ERROR`/`SAFETY_BLOCKED`/`CLEANUP_FAILED`) never trip. Complements single-point `Unknown-state execution handling` (stop on one unknown step) by adding a recurring same-failure threshold stop. **Next action:** wire into `layer_subplans`/`pipeline_runner` self-heal loops and add a `quality-gate` blocker; currently only tests import it. |
| Differential testing (old/new output compare) | Not started | — | No interface-level old-vs-new output diff exists; `visual-compare` covers screenshots only. The capture→model→reconcile base is a natural fit for migration/refactor regression and is tracked as a candidate P1, not yet implemented. |
| Property-based testing (bulk boundary inputs) | Not started | — | `core/invariants.py` and `core/adversarial.py` provide invariant/adversarial seeds, but no bulk boundary-input generator exists. Deprioritized for a business-flow tool. |
| Soak aggregation and run evidence | Implemented | contract/workspace | `crosscheck soak-report` aggregates consecutive run `summary.json` files into stability, per-case pass rate, asset usage and `soak_runs`; the quality gate auto-consumes the soak summary as run evidence. |

## Verification levels

- `contract`: deterministic offline code/schema behavior.
- `local_e2e`: local mock or SQLite integration path.
- `external_ready`: external evidence can be consumed; it is not a current external PASS.
- `external_pass`: current real-system evidence is independently reviewable.

The implementation must not promote a lower level by changing report wording.
