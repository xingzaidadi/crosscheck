"""Observe-plan-act-verify runtime with bounded recovery and evidence."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.ui_agent.observer import observe, wait_for_settle
from core.ui_agent.planner import ObservationPlanner, PlannerDecision
from core.ui_agent.recovery import recover_and_click
from core.ui_agent.risk_policy import assess_action
from core.ui_agent.verifier import verify
from scripts.ui_test import _execute_structured_action
from core.ui_actions import replay
from core.ui_agent.provider import planner_provider
from core.ui_agent.capabilities import accessibility_audit, browser_quality, semantic_map, write_json


# ── 缺陷2a:导航后置条件 ─────────────────────────────────────────────
# "点击成功"只证明按钮被点,不证明到达目标页。下列 helper 在导航意图动作后
# 验证页面是否真的改变(URL 变化 或 页面签名变化)。拿不到可比信号 → INCONCLUSIVE,
# 页面毫无变化 → FAILED。绝不把"点了没反应"当 PASSED。

_NAV_TARGET_TERMS = ("详情", "明细", "记录", "detail", "record")


def _navigation_intent(decision) -> bool:
    """该决策是否带"到达某页/某目标"的导航意图。

    认两类:desired_action 为 reach;或 click 的目标像页面/菜单导航(由 planner 的
    desired_action.action 标注)。纯 in-page 操作(筛选、勾选、输入)不在此列,避免误伤。
    """
    desired = getattr(decision, "desired_action", None) or {}
    action = str(desired.get("action") or "")
    if action == "reach":
        return True
    if action == "open_first_record":
        return True
    # click 明确声明要进入目标页(target/text 含页面语义词)时也算导航意图
    if action == "click":
        target = str(desired.get("target") or desired.get("text") or "")
        if any(term in target for term in _NAV_TARGET_TERMS):
            return True
    return False


def _navigation_target_text(decision) -> str:
    """取导航意图的目标文本(用于幂等导航判定)。

    优先 desired_action.target,其次 desired_action.text,再退回实际 action 的 text/label。
    这是"该到达哪个视图"的人类可读标签,与页面 headings 做包含比对。
    """
    desired = getattr(decision, "desired_action", None) or {}
    for key in ("target", "text", "label"):
        value = str(desired.get(key) or "").strip()
        if value:
            return value
    action = getattr(decision, "action", None) or {}
    for key in ("text", "label", "target"):
        value = str(action.get(key) or "").strip()
        if value:
            return value
    return ""


def _navigation_key(decision) -> str:
    """导航动作的稳定标识(用于识别"同一导航被重复下发")。

    = 目标文本(若有)| 否则取 desired_action.action 名(如 open_first_record)。
    planner 常把同一逻辑导航连下两次:首次真到达,次次是对已打开目标的幂等重点击。
    用这个 key 记"哪些导航已成功到达",次次无变化时据此判幂等而非假 FAILED。
    """
    text = _navigation_target_text(decision)
    if text:
        return f"text:{text}"
    desired = getattr(decision, "desired_action", None) or {}
    action_name = str(desired.get("action") or "").strip()
    if action_name:
        return f"action:{action_name}"
    return ""


def _page_signature(page) -> dict:
    """抓一个轻量页面签名:URL + 正文长度 + 可见标题文本集合。防御性,任何异常都降级。"""
    sig = {"url": "", "body_len": -1, "headings": ""}
    try:
        sig["url"] = page.url
    except Exception:
        pass
    try:
        body = page.locator("body")
        text = body.inner_text(timeout=2000) if body.count() else ""
        sig["body_len"] = len(text.strip())
    except Exception:
        pass
    try:
        headings = page.locator("h1,h2,h3,[role='heading']").all_inner_texts()
        sig["headings"] = "|".join(sorted(str(h).strip() for h in headings))[:2000]
    except Exception:
        pass
    return sig


def _settle_and_reacquire(page):
    """点击后等待稳定,并在开新标签页时切到最新页。"""
    try:
        page.wait_for_timeout(250)
        pages = page.context.pages
        if pages and pages[-1] != page:
            page = pages[-1]
            page.wait_for_load_state("domcontentloaded", timeout=10000)
        wait_for_settle(page)
    except Exception:
        pass
    return page


def _verify_navigation(page, before: dict | None, target_text: str = "",
                       already_reached: bool = False) -> dict:
    """比对导航前后签名,返回 {status, reason}。

    - URL 变化 或 页面签名(正文长度/标题)变化 → PASSED(确实跳转/切换视图)。
    - 没变,但目标视图已在页面标题中(幂等导航:目标此前已被打开,再点无新变化)
      → PASSED(到达即成功,不因重复点击而假 FAILED)。
    - 没变,且本次运行里**同一导航此前已成功到达过**(planner 把同一导航重复下发)
      → PASSED(幂等重点击,非假通过)。
    - 既没变、目标视图也不在页面上、此前也没到达过 → FAILED(点击等于空操作)。
    - 拿不到有效的 before/after 签名 → INCONCLUSIVE(不凭空判成功)。

    『目标在页面标题中』只认 h1/h2/h3/role=heading 这类**内容视图**标志,
    不认仍挂在导航区的可点控件——审计假通过场景(点"订单中心"仍停在工作台、
    页面只剩"工作台"标题)里目标并不会出现在 headings,故仍如实判 FAILED。
    """
    if not before:
        return {"status": "INCONCLUSIVE", "reason": "navigation baseline unavailable; cannot confirm arrival"}
    after = _page_signature(page)
    if before.get("url") and after.get("url") and before["url"] != after["url"]:
        return {"status": "PASSED", "reason": f"url changed: {before['url']} -> {after['url']}"}
    # URL 未变(SPA 内切换):看页面签名是否变化
    before_body = before.get("body_len", -1)
    after_body = after.get("body_len", -1)
    headings_changed = (before.get("headings") or "") != (after.get("headings") or "")
    body_changed = before_body >= 0 and after_body >= 0 and before_body != after_body
    if headings_changed or body_changed:
        return {"status": "PASSED", "reason": "page view changed after navigation click"}
    # 幂等导航:页面没变,但目标内容视图已经在标题里(此前已到达)。
    target_text = (target_text or "").strip()
    after_headings = after.get("headings") or ""
    if target_text and after_headings and target_text in after_headings:
        return {"status": "PASSED",
                "reason": f"target view '{target_text}' already present (idempotent navigation, already arrived)"}
    # 幂等导航:同一导航本次运行此前已成功到达过,planner 又重复下发同一动作。
    if already_reached:
        return {"status": "PASSED",
                "reason": "navigation already reached earlier this run; redundant re-trigger produced no new change"}
    if after_body < 0 and after.get("url") in ("", None):
        return {"status": "INCONCLUSIVE", "reason": "post-click page signature unavailable; cannot confirm arrival"}
    return {"status": "FAILED",
            "reason": "navigation click had no effect: still on same URL and page view unchanged (did not reach target)"}


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
            # 等微前端/SPA 子应用挂载稳定后再观察,否则只能快照到"加载中"外壳(确定性、
            # 零业务;超时不阻断,照常观察)。
            wait_for_settle(page)
            current_observation = observe(page)
            current_observation["screenshot"] = str(output / "before.png")
            result.observations.append(current_observation)
            result.page_maps.append(semantic_map(current_observation))
            self._capture(page, output, "before", result)
            planner = ObservationPlanner(plan.source_instruction, plan.actions, resolver=planner_provider())
            reached_nav_keys: set[str] = set()
            nav_progress_made = False
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
                # 缺陷2a:导航意图动作必须有"到达目标"的后置条件。点击只能证明"点了",
                # 不能证明"到了"。先快照导航前的 URL+页面签名,点击后比对是否真的跳转。
                nav_intent = _navigation_intent(decision)
                nav_before = _page_signature(page) if nav_intent else None
                nav_target = _navigation_target_text(decision) if nav_intent else ""
                nav_key = _navigation_key(decision) if nav_intent else ""
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
                # 缺陷2a:导航意图动作在 mark_success 前必须验证"确实到达"。
                # 先让页面稳定,再比对导航前后的 URL+页面签名:都没变 → 点击等于空操作,
                # 判 FAILED(不是 PASSED);拿不到可比信号 → INCONCLUSIVE,绝不冒充成功。
                # 但**仅对必测(非 explore)导航**硬判:探索性探针(plan_kind==explore)点到
                # 死胡同(如面板已打开、再点无变化)不是"假通过",只记录证据不连累整体,
                # 与下方 line『explore 失败→BLOCKED 不 FAILED』的既有尺度一致。
                if nav_intent:
                    page = _settle_and_reacquire(page)
                    already_reached = bool(nav_key) and nav_key in reached_nav_keys
                    verdict = _verify_navigation(page, nav_before, nav_target, already_reached)
                    row["navigation_check"] = verdict
                    # 导航后置条件是堵『零进展假通过』的闸:审计里"点订单中心→毫无反应→仍判 PASSED"
                    # 正是全程零导航进展。一旦本次运行已有任一导航真正到达过内容(nav_progress_made),
                    # 后续同类动作的无变化多为 planner 对已到达目标的幂等重触发——不再由导航闸硬判,
                    # 交给结尾的 oracle 断言做权威判定(断言不达照样 FAILED,不漏)。
                    is_required_nav = row.get("plan_kind") != "explore"
                    if is_required_nav and verdict["status"] == "FAILED" and not nav_progress_made:
                        result.status = "FAILED"
                        result.error = verdict["reason"]
                        break
                    if is_required_nav and verdict["status"] == "INCONCLUSIVE" and not nav_progress_made:
                        result.status = "INCONCLUSIVE"
                        result.error = verdict["reason"]
                        break
                    if verdict["status"] == "PASSED":
                        nav_progress_made = True
                        if nav_key:
                            reached_nav_keys.add(nav_key)
                planner.mark_success(PlannerDecision(
                    kind=result.planner_decisions[-1]["kind"], action=action,
                    reason=result.planner_decisions[-1]["reason"],
                    confidence=result.planner_decisions[-1]["confidence"],
                    desired_action=result.planner_decisions[-1].get("desired_action"),
                    source=result.planner_decisions[-1].get("source", ""),
                ))
                if action.get("action") == "observe" and not planner.state.pending_actions:
                    break
                page.wait_for_timeout(250)
                pages = page.context.pages
                if pages and pages[-1] != page:
                    page = pages[-1]
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                wait_for_settle(page)
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
            decisions_path = write_json(output / "planner-decisions.json",
                                        self._decision_log(result))
            result.evidence.extend([map_path, quality_path, decisions_path])
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
    def _decision_log(result: AgentRuntimeResult) -> list[dict[str, Any]]:
        """把每步 planner 决策整理成可复盘的明细:选了哪个控件、为什么、
        候选都打了几分、判定来源(确定性/同义/provider)。这是"打开 planner
        黑盒"的单独产物,与 trace.json 互补。"""
        log: list[dict[str, Any]] = []
        for index, decision in enumerate(result.planner_decisions, 1):
            action = decision.get("action") or {}
            chosen = str(action.get("text") or action.get("label") or action.get("target") or "")
            candidates = decision.get("candidates") or []
            top = candidates[0] if candidates else None
            # 判定来源:优先用 planner 显式标注的 source(provider=可选插件/LLM),
            # 缺失时按确定性候选打分回推(精确/别名 vs 子串 vs 弱词重合)。
            top_score = float((top or {}).get("score") or 0)
            if decision.get("source") == "provider":
                source = "provider"
            elif decision.get("kind") == "explore" and decision.get("confidence", 0) and not candidates:
                source = "provider"
            elif top_score >= 100.0:
                source = "exact_or_alias"
            elif top_score >= 70.0:
                source = "substring"
            else:
                source = "deterministic"
            log.append({
                "step": index,
                "kind": decision.get("kind"),
                "chosen": chosen,
                "reason": decision.get("reason"),
                "confidence": decision.get("confidence"),
                "desired": decision.get("desired_action"),
                "candidates": candidates,
                "source": source,
            })
        return log

    @staticmethod
    def _capture(page, output: Path, name: str, result: AgentRuntimeResult) -> None:
        screenshot = output / f"{name}.png"
        dom = output / f"{name}.html"
        page.screenshot(path=str(screenshot), full_page=True)
        dom.write_text(page.content(), encoding="utf-8")
        result.evidence.extend([str(screenshot), str(dom)])
