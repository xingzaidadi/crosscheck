"""Observe-plan-act-verify runtime with bounded recovery and evidence."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.ui_agent.observer import observe
from core.ui_agent.planner import ObservationPlanner, PlannerDecision
from core.ui_agent.recovery import recover_and_click
from core.ui_agent.risk_policy import assess_action
from core.ui_agent.verifier import verify
from scripts.ui_test import _execute_structured_action
from core.ui_actions import replay
from core.ui_agent.provider import planner_provider
from core.ui_agent.capabilities import accessibility_audit, browser_quality, semantic_map, write_json


@dataclass
class AgentRuntimeResult:
    status: str
    actions: list[dict[str, Any]] = field(default_factory=list)
    assertions: list[dict[str, Any]] = field(default_factory=list)
    recovery_events: list[dict[str, Any]] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    planner_decisions: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    page_maps: list[dict[str, Any]] = field(default_factory=list)
    accessibility: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class AgentRuntime:
    def __init__(self, *, policy: str = "read_only", allow_write: bool = False,
                 write_scope: str = "", max_steps: int = 20):
        self.policy = policy
        self.allow_write = allow_write
        self.write_scope = write_scope
        self.max_steps = max_steps

    @staticmethod
    def _assertions_complete(result: AgentRuntimeResult) -> bool:
        return bool(result.assertions) and all(item.get("passed") is True for item in result.assertions)

    def run(self, page, plan, evidence_dir: str | Path) -> AgentRuntimeResult:
        output = Path(evidence_dir)
        output.mkdir(parents=True, exist_ok=True)
        result = AgentRuntimeResult(status="RUNNING")
        console_errors: list[dict[str, Any]] = []
        page_errors: list[dict[str, Any]] = []
        failed_requests: list[dict[str, Any]] = []
        try:
            page.on("console", lambda message: console_errors.append({
                "type": message.type, "text": message.text[:500]
            }) if message.type == "error" else None)
            page.on("pageerror", lambda error: page_errors.append({"text": str(error)[:500]}))
            page.on("requestfailed", lambda request: failed_requests.append({
                "method": request.method, "url": request.url, "failure": str(request.failure)
            }))
            if page.url != plan.url:
                page.goto(plan.url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(500)
            current_observation = observe(page)
            current_observation["screenshot"] = str(output / "before.png")
            result.observations.append(current_observation)
            result.page_maps.append(semantic_map(current_observation))
            self._capture(page, output, "before", result)
            planner = ObservationPlanner(plan.source_instruction, plan.actions, resolver=planner_provider())
            for index in range(1, self.max_steps + 1):
                if not planner.state.pending_actions:
                    break
                decision = planner.decide(current_observation)
                result.planner_decisions.append(decision.to_dict())
                if decision.kind == "blocked" or not decision.action:
                    if planner.mark_blocked(decision, current_observation):
                        continue
                    result.status = "BLOCKED"
                    result.error = decision.reason
                    break
                action = decision.action
                decision = assess_action(action, policy=self.policy, allow_write=self.allow_write,
                                         write_scope=self.write_scope)
                row = {"step": index, "action": action, "plan_kind": result.planner_decisions[-1]["kind"],
                       "risk": asdict(decision), "ok": False}
                if not decision.allowed:
                    row["error"] = decision.reason
                    result.actions.append(row)
                    result.status = "BLOCKED"
                    result.error = decision.reason
                    break
                if action.get("action") == "observe":
                    row["ok"] = True
                elif action.get("action") == "click":
                    recovery = recover_and_click(
                        page, str(action.get("text") or ""),
                        record=lambda event: result.recovery_events.append({"step": index, **event}),
                    )
                    row.update({"ok": recovery["ok"], "strategy": recovery["strategy"]})
                    if not recovery["ok"]:
                        row["error"] = recovery.get("error")
                elif action.get("action") in {"text", "number", "textarea", "select", "search_select",
                                               "cascader", "date", "grid_cell", "hover", "check", "uncheck",
                                               "press", "fill", "upload", "download", "frame_click", "frame_fill"}:
                    runtime_action = dict(action)
                    if runtime_action.get("action") == "download":
                        runtime_action.setdefault("output_dir", str(output / "downloads"))
                    replayed = replay(page, [runtime_action])
                    executed = replayed[0] if replayed else {"ok": False, "error": "action produced no result"}
                    row.update(executed)
                else:
                    try:
                        executed = _execute_structured_action(page, action)
                    except Exception as exc:
                        executed = {"ok": False, "error": str(exc)[:300], "recovery_attempted": True}
                    row.update(executed)
                result.actions.append(row)
                if not row.get("ok"):
                    result.status = "BLOCKED" if row.get("plan_kind") == "explore" else "FAILED"
                    result.error = str(row.get("error") or "action failed")
                    break
                planner.mark_success(PlannerDecision(
                    kind=result.planner_decisions[-1]["kind"], action=action,
                    reason=result.planner_decisions[-1]["reason"],
                    confidence=result.planner_decisions[-1]["confidence"],
                    desired_action=result.planner_decisions[-1].get("desired_action"),
                ))
                if action.get("action") == "observe" and not planner.state.pending_actions:
                    break
                page.wait_for_timeout(250)
                pages = page.context.pages
                if pages and pages[-1] != page:
                    page = pages[-1]
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                current_observation = observe(page)
                result.page_maps.append(semantic_map(current_observation))
                step_screenshot = output / f"step-{index:02d}.png"
                page.screenshot(path=str(step_screenshot), full_page=True)
                result.evidence.append(str(step_screenshot))
                current_observation["screenshot"] = str(step_screenshot)
                result.observations.append(current_observation)
            # Always capture a final state, including BLOCKED/FAILED runs.  A
            # stopped action must not suppress the evidence needed to explain
            # the failure or diagnose the application itself.
            try:
                page.wait_for_timeout(150)
                current_observation = observe(page)
                result.observations.append(current_observation)
                result.page_maps.append(semantic_map(current_observation))
            except Exception as exc:
                result.error = result.error or f"final observation failed: {exc}"
            result.assertions = verify(page, plan.oracles, plan.source_instruction)
            result.accessibility = accessibility_audit(page)
            result.quality = browser_quality(
                page, console_errors=console_errors, page_errors=page_errors,
                failed_requests=failed_requests,
                thresholds=getattr(plan, "quality_thresholds", {}) or {},
            )
            map_path = write_json(output / "semantic-map.json", result.page_maps)
            quality_path = write_json(output / "quality.json", {
                "accessibility": result.accessibility, "quality": result.quality,
            })
            result.evidence.extend([map_path, quality_path])
            final_decision = planner.decide(
                current_observation,
                assertions_passed=all(item.get("passed") is True for item in result.assertions),
            )
            result.planner_decisions.append(final_decision.to_dict())
            self._capture(page, output, "after", result)
            goals_complete = not planner.state.pending_actions and final_decision.kind in {"complete", "verify"}
            assertions_passed = self._assertions_complete(result)
            if result.quality.get("threshold_failures"):
                assertions_passed = False
            if result.status in {"BLOCKED", "FAILED"}:
                result.error = result.error or "execution stopped before all goals completed"
            elif plan.unresolved_expectations:
                result.status = "INCONCLUSIVE"
            elif not result.assertions:
                result.status = "INCONCLUSIVE"
                result.error = result.error or "no objective UI assertions were executed"
            elif goals_complete and assertions_passed:
                result.status = "PASSED"
            else:
                result.status = "FAILED"
            if plan.unresolved_expectations:
                result.error = "unresolved expectations: " + "; ".join(plan.unresolved_expectations)
        except Exception as exc:
            result.status = "ENV_ERROR"
            result.error = str(exc)[:500]
        trace = output / "trace.json"
        trace.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        result.evidence.append(str(trace))
        return result

    @staticmethod
    def _capture(page, output: Path, name: str, result: AgentRuntimeResult) -> None:
        screenshot = output / f"{name}.png"
        dom = output / f"{name}.html"
        page.screenshot(path=str(screenshot), full_page=True)
        dom.write_text(page.content(), encoding="utf-8")
        result.evidence.extend([str(screenshot), str(dom)])
