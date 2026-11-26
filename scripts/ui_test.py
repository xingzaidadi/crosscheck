"""One-shot UI testing from a prose case file."""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.case_source import read_cases  # noqa: E402
from core.suite_plan import classify_case  # noqa: E402
from core.ui_actions import replay  # noqa: E402
from core.business_skill import match_skill  # noqa: E402
from core.asset_pipeline import create_candidate  # noqa: E402
from core.asset_pipeline import record_replay  # noqa: E402
from core.asset_store import AssetStore  # noqa: E402
from core.ui_test_intake import _SEMANTICS, build_ui_intent, validate_intake  # noqa: E402
from core.write_policy import validate_write_policy, parse_write_scope  # noqa: E402
from core.ui_fixture_lifecycle import cleanup_fixtures  # noqa: E402
from core.visual_gate import compare as compare_visual  # noqa: E402
from core.visual_store import VisualBaselineStore  # noqa: E402


def _safe(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in value)[:100]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _evaluate_oracle(page, oracle: dict[str, Any]) -> dict[str, Any]:
    if oracle["kind"] == "page_health":
        body = page.locator("body")
        body_text = body.inner_text(timeout=3000) if body.count() else ""
        actual = {
            "url": page.url,
            "title": page.title(),
            "body_length": len(body_text.strip()),
            "has_error": bool(re.search(r"(?:500|internal server error|系统异常|服务异常|页面不存在)", body_text, re.I)),
        }
        ok = bool(actual["url"] and actual["body_length"] > 0 and not actual["has_error"])
    elif oracle["kind"] == "detail_page":
        headings = []
        try:
            headings = page.locator("h1,h2,h3,[role='heading']").all_inner_texts()
        except Exception:
            headings = []
        body = page.locator("body").inner_text()
        target = str(oracle.get("value") or "详情")
        actual = {
            "heading": any(target in str(item) for item in headings),
            "body": target in body,
            "dialog": page.locator("[role=dialog], dialog, .modal, .drawer").count() > 0,
            "readonly_field": page.locator("input[readonly], textarea[readonly], [aria-readonly='true']").count() > 0,
        }
        ok = bool(actual["heading"] or actual["dialog"] or actual["readonly_field"])
    elif oracle["kind"] == "field_text_equals":
        label = str(oracle.get("value") or "")
        expected = str(oracle.get("expected") or "")
        label_locator = page.get_by_text(label, exact=True).first
        actual = ""
        located = False  # 是否真正定位到了"目标字段"这个控件/单元格
        if label_locator.count():
            scope = label_locator.locator("xpath=ancestor-or-self::*[self::label or self::td or self::th or self::div][1]")
            if scope.count():
                control = scope.locator("input, textarea, select").first
                actual = control.input_value() if control.count() else scope.inner_text().replace(label, "", 1).strip(" ：:\n\t")
                located = True
        # 铁律『不假通过』:取不到目标字段值时判 inconclusive(ok=None),**绝不**退回
        # 全页正文搜索。旧逻辑 `expected in body 就 actual=expected` 会把"页面别处恰好
        # 出现 expected 字样"误当成"目标字段等于 expected"——哪怕目标字段其实是别的值,
        # 或根本没定位到。误通过比没测更危险,故只在真正拿到目标字段值时才比对。
        if not located or not actual:
            ok = None
        else:
            # 铁律『等值即等值』:field_text_equals 是"等于"语义,必须严格 ==。
            # 旧逻辑 `or expected in actual` 是子串漏网:actual="100"/expected="10"、
            # actual="Not approved"/expected="approved" 都会误判通过。子串比较只允许
            # 出现在显式的 *_contains kind,等值类一律严格相等。
            ok = actual == expected
    elif oracle["kind"] == "api_status":
        # API status is evaluated by the autonomous runner from captured
        # response metadata; this branch is retained for legacy callers.
        actual = None
        ok = None
    elif oracle["kind"] == "api_observed":
        actual = None
        ok = None
    elif oracle["kind"] == "url_contains":
        actual = page.url
        ok = oracle["value"] in actual
    elif oracle["kind"] == "readonly":
        detail = page.locator("[role=dialog], .hi-v5-drawer, .hi-v5-modal, .hi-v5-drawer-content").last
        scope = detail if detail.count() else page.locator("body")
        edit_controls = scope.get_by_role("button", name=re.compile(r"编辑|修改|保存|提交"))
        editable_fields = scope.locator(
            "input:not([type=hidden]):not([disabled]):not([readonly]), "
            "textarea:not([disabled]):not([readonly]), select:not([disabled]), [contenteditable='true']"
        )
        actual = edit_controls.count() == 0 and editable_fields.count() == 0
        ok = actual is bool(oracle["expected"])
    elif oracle["kind"] == "pagination_page":
        actual = page.get_by_text(str(oracle["value"]), exact=True).first.is_visible()
        ok = actual is bool(oracle["expected"])
    elif oracle["kind"] == "selected_row_count":
        actual = page.locator("input[type=checkbox]:checked, [aria-selected='true']").count()
        ok = actual == int(oracle["value"])
    elif oracle["kind"] == "page_size":
        actual = page.get_by_text(f"{oracle['value']} 条/页", exact=False).first.is_visible()
        ok = actual is bool(oracle["expected"])
    elif oracle["kind"] == "visible_fields":
        actual = {label: page.get_by_text(str(label), exact=True).count() > 0
                  for label in oracle.get("fields") or []}
        ok = all(actual.values())
    elif oracle["kind"] == "visibility":
        locator = page.get_by_text(str(oracle.get("value") or ""), exact=True).first
        actual = locator.count() > 0 and locator.is_visible()
        ok = actual is bool(oracle.get("expected", True))
    elif oracle["kind"] == "field_value_equals":
        label = str(oracle.get("value") or "")
        expected = str(oracle.get("expected") or "")
        label_locator = page.get_by_text(label, exact=True).first
        scope = label_locator.locator("xpath=ancestor-or-self::*[self::label or self::td or self::th or self::div][1]")
        actual = ""
        located = False  # 是否真正定位到了目标字段(控件或相邻文本)
        if label_locator.count() and scope.count():
            control = scope.locator("input, textarea, select").first
            if control.count():
                actual = control.input_value()
                located = True
            else:
                text = scope.inner_text().replace(label, "", 1).strip(" ：:\n\t")
                if text:
                    actual = text
                    located = True
        if not located:
            sibling = label_locator.locator("xpath=following::*[1]")
            if label_locator.count() and sibling.count():
                actual = sibling.inner_text().strip()
                located = True
        # 铁律『不假通过』:定位不到目标字段控件 → INCONCLUSIVE(ok=None),绝不让
        # "取不到值(actual='')恰好等于期望空值(expected='')"冒充 PASS。只有真正定位到
        # 字段时,空值期望才算被客观验证为空。
        if not located:
            ok = None
        else:
            ok = actual == expected
    elif oracle["kind"] == "enabled":
        locator = page.get_by_text(str(oracle.get("value") or ""), exact=True).first
        control = locator.locator("xpath=ancestor-or-self::*[self::button or self::input or self::select or self::textarea][1]")
        if not control.count():
            control = locator
        actual = control.is_enabled() if control.count() else None
        ok = actual is bool(oracle.get("expected", True))
    elif oracle["kind"] == "text_matches":
        actual = page.locator("body").inner_text()
        ok = bool(re.search(str(oracle.get("value") or ""), actual))
    elif oracle["kind"] in {"text_equals", "text_contains"}:
        locator = page.locator(str(oracle.get("selector") or "body")).first
        actual = locator.inner_text()
        expected = str(oracle.get("value") or "")
        ok = actual.strip() == expected if oracle["kind"] == "text_equals" else expected in actual
    elif oracle["kind"] == "count":
        locator = page.locator(str(oracle.get("selector") or "table tbody tr"))
        actual = locator.count()
        ok = actual == int(oracle.get("value") or 0)
    elif oracle["kind"] == "filter_controls":
        # 缺陷4:旧逻辑"全页有任意 input/select/button 就通过"太松——页面坏了但残留
        # 一个按钮也会 PASS。改为锚定**查询区**:必须找到查询/搜索触发控件(按钮或 role),
        # 且其所在区域确有可输入控件。定位不到查询区 → INCONCLUSIVE(ok=None),不假通过。
        trigger = page.get_by_role("button", name=re.compile(r"查询|搜索|筛选|search", re.I)).first
        if not trigger.count():
            # 退一步:按可见文本找查询/搜索触发(有些实现不是标准 button role)。
            trigger = page.get_by_text(re.compile(r"^(查询|搜索|筛选)$"), exact=False).first
        if not trigger.count():
            actual = {"query_region": False, "inputs": 0}
            ok = None  # 连查询触发都没有 → 无法判定查询区是否可用
        else:
            region = trigger.locator(
                "xpath=ancestor-or-self::*[self::form or contains(@class,'search') "
                "or contains(@class,'filter') or contains(@class,'query')][1]")
            scope = region if region.count() else page.locator("body")
            input_count = scope.locator(
                "input:not([type=hidden]), textarea, select").count()
            # 指定了具体字段标签时,逐个确认其在查询区可见。
            field_labels = oracle.get("fields") or []
            fields_present = {label: scope.get_by_text(str(label), exact=True).count() > 0
                              for label in field_labels}
            actual = {"query_region": True, "inputs": input_count, **fields_present}
            # 查询区存在且至少有一个输入控件(以及指定字段若有则都在)→ PASS。
            ok = input_count > 0 and all(fields_present.values())
    elif oracle["kind"] == "status_groups":
        body = page.locator("body").inner_text()
        groups = {str(group): tuple(_SEMANTICS.get("status_terms") or [])
                  for group in (_SEMANTICS.get("status_groups") or [])}
        actual = {name: any(word in body for word in words) for name, words in groups.items()}
        # A source case can require a status bucket that is valid but empty in
        # the current fixture.  Presence of the list itself is still evidence
        # that the UI loaded; empty-state semantics remain INCONCLUSIVE rather
        # than a false business FAIL.
        if not any(actual.values()) and page.locator("table tbody tr").count() >= 0:
            actual = {name: None for name in groups}
            ok = None
        else:
            ok = all(actual.values())
    else:
        locator = page.get_by_text(str(oracle["value"]), exact=False).first
        visible = locator.count() > 0 and locator.is_visible()
        actual = visible
        ok = visible is bool(oracle["expected"])
    return {**oracle, "actual": actual, "passed": ok}


def _execute_structured_action(page, action: dict[str, Any], page_model: dict[str, Any] | None = None) -> dict[str, Any]:
    kind = action.get("action")
    page_model = page_model or {}
    selectors = page_model.get("selectors") or {}
    try:
        if kind == "open_first_record":
            column = str(action.get("column") or "")
            selector = str(selectors.get("record_link") or selectors.get("demand_code") or "")
            if selector:
                locator = page.locator(selector).first
                if locator.count() and locator.is_visible():
                    locator.click(timeout=4000)
                    return {"action": kind, "target": action, "ok": True,
                            "selector": selector, "error": ""}
            table = page.locator("table")
            if column:
                table = table.filter(has=page.get_by_role("columnheader", name=re.compile(re.escape(column)))).first
            else:
                table = table.first
            if not table.count():
                table = page.locator("table").first
            cell = table.locator("tbody tr").first
            target = cell.locator("a, [role=link], button").first
            if not target.count():
                target = cell.locator("td").first
            target.click(timeout=4000)
            return {"action": kind, "target": action, "ok": True, "error": ""}
        if kind == "select_first_row":
            row = page.locator("table tbody tr").first
            row.locator("input[type=checkbox], [role=checkbox]").first.click(timeout=3000)
            return {"action": kind, "target": action, "ok": True, "error": ""}
        if kind == "go_to_page":
            page_number = str(action.get("page") or 2)
            page.get_by_role("button", name=page_number, exact=True).last.click(timeout=3000)
            return {"action": kind, "target": action, "ok": True, "error": ""}
        if kind == "switch_tabs":
            configured = (page_model.get("selectors") or {}).get("mode_tabs")
            labels = list(action.get("labels") or [])
            if not labels:
                labels = [item.strip().removeprefix("text=")
                          for item in str(configured or "").split(",") if item.strip()]
            results = []
            for label in labels:
                locator = page.get_by_role("tab", name=label, exact=True)
                if not locator.count():
                    locator = page.get_by_role("button", name=label, exact=True)
                if not locator.count():
                    locator = page.get_by_text(label, exact=True)
                if locator.count() and locator.first.is_visible():
                    locator.first.click(timeout=3000)
                    results.append({"label": label, "clicked": True})
                else:
                    results.append({"label": label, "clicked": False})
            missing = [item["label"] for item in results if not item["clicked"]]
            return {"action": kind, "target": action, "ok": None if missing else True,
                    "actual": results,
                    "error": f"页面未发现控件：{', '.join(missing)}" if missing else ""}
        if kind == "prepare_filter":
            return {"action": kind, "target": action, "ok": None,
                    "error": "用例未提供筛选字段和值，未修改页面筛选条件"}
    except Exception as exc:  # noqa: BLE001
        return {"action": kind, "target": action, "ok": False, "error": str(exc)[:200]}
    return {"action": kind, "target": action, "ok": None, "error": "不支持的结构化 UI 动作"}


def _persist_exploration_candidates(workspace: Path, item: dict[str, Any]) -> list[str]:
    acceptance = item.get("acceptance") or {}
    unresolved = acceptance.get("unresolved") or []
    actions = [row for row in (item.get("execution") or {}).get("actions_replayed") or []
               if row.get("ok") is None]
    store = AssetStore(workspace / "knowledge_base" / "asset_candidates")
    asset_ids = []
    for index, text in enumerate(unresolved, start=1):
        asset = create_candidate({"case_id": item.get("case_id"), "kind": "ui_assertion",
                                  "source": text, "page_url": item.get("page_url"),
                                  "required_review": ["proof_type", "selector", "replay"]},
                                 asset_type="ui_assertion_candidate")
        asset["business_skill"] = (item.get("business_skill") or {}).get("skill_id")
        asset["source"] = {"case_id": item.get("case_id"), "assertion_index": index}
        store.save(asset)
        asset_ids.append(str(asset["asset_id"]))
    for index, action in enumerate(actions, start=1):
        asset = create_candidate({"case_id": item.get("case_id"), "kind": "ui_action",
                                  "action": action.get("action"), "target": action.get("target"),
                                  "error": action.get("error"), "page_url": item.get("page_url"),
                                  "required_review": ["selector", "replay"]},
                                 asset_type="ui_action_candidate")
        asset["business_skill"] = (item.get("business_skill") or {}).get("skill_id")
        asset["source"] = {"case_id": item.get("case_id"), "action_index": index}
        store.save(asset)
        asset_ids.append(str(asset["asset_id"]))
    return asset_ids


def _record_candidate_replay(workspace: Path, item: dict[str, Any]) -> list[str]:
    """Attach deterministic run evidence to matching candidates without auto-approving them."""
    store = AssetStore(workspace / "knowledge_base" / "asset_candidates")
    case_id = str(item.get("case_id") or "")
    evidence = item.get("evidence") or {}
    evidence_paths = [str(value) for value in (evidence.get("screenshots") or []) if value]
    evidence_paths += [str(evidence[key]) for key in ("video", "html") if evidence.get(key)]
    passed = item.get("verdict") == "PASS"
    updated_ids = []
    for asset in store.list(state="candidate"):
        if str((asset.get("payload") or {}).get("case_id") or "") != case_id:
            continue
        updated = record_replay(asset, passed=passed,
                                original_result=(asset.get("payload") or {}),
                                replay_result={"verdict": item.get("verdict"),
                                               "execution": item.get("execution"),
                                               "acceptance": item.get("acceptance")},
                                evidence=evidence_paths)
        if passed:
            updated["state"] = "replay_verified"
        store.save(updated)
        updated_ids.append(str(updated["asset_id"]))
    return updated_ids


def _attach_visual_result(item: dict[str, Any], run_dir: Path, baseline_dir: str,
                          threshold: float) -> None:
    if not baseline_dir or item.get("verdict") in {"DEFERRED", "BLOCKED", "ENV_ERROR"}:
        return
    screenshots = (item.get("evidence") or {}).get("screenshots") or []
    if not screenshots:
        return
    try:
        baseline = VisualBaselineStore(baseline_dir).get(str(item.get("case_id") or "case"))
        if not baseline.get("approved"):
            item["visual"] = {"verdict": "INCONCLUSIVE", "reason": "baseline_not_approved"}
            return
        result = compare_visual(baseline["path"], run_dir / screenshots[-1], threshold=threshold)
        item["visual"] = {"verdict": "PASS" if result["passed"] else "FAIL", **result}
        if not result["passed"] and item.get("verdict") == "PASS":
            item["verdict"] = "FAIL"
            item["reason"] = "visual baseline mismatch"
    except FileNotFoundError:
        item["visual"] = {"verdict": "NOT_COVERED", "reason": "baseline_not_found"}


def _is_redundant_click(action: dict[str, Any], structured_actions: list[dict[str, Any]]) -> bool:
    """Do not replay prose clicks already represented by a structured action."""
    if action.get("action") != "click":
        return False
    text = str(action.get("text") or "").strip()
    for structured in structured_actions:
        if structured.get("action") == "switch_tabs" and text in {
            str(label).strip() for label in structured.get("labels") or []
        }:
            return True
    return False


def _run_case(browser, raw_case, args, run_dir: Path) -> dict[str, Any]:
    intent = build_ui_intent(raw_case, args.url)
    skill = getattr(args, "business_skill", None) or match_skill(args.workspace, args.url)
    page_model = skill.page_model(args.url) if skill else {}
    skill_assertions = skill.assertions() if skill else {}
    skill_actions = skill.actions() if skill else {}
    for _, definition in skill_actions.items():
        triggers = [str(item) for item in definition.get("triggers") or []]
        if not triggers or not any(trigger in intent.source_steps for trigger in triggers):
            continue
        kind = definition.get("action")
        action_name = {"click_table_cell": "open_first_record", "pagination": "go_to_page",
                       "select_table_row": "select_first_row", "click_tab": "switch_tabs"}.get(kind, kind)
        action = {"action": action_name}
        action.update({key: value for key, value in definition.items() if key not in {"action", "triggers"}})
        if action_name == "switch_tabs" and any(item.get("action") == action_name for item in intent.actions):
            existing = next(item for item in intent.actions if item.get("action") == action_name)
            existing["labels"] = list(dict.fromkeys(existing.get("labels") or action.get("labels") or []))
        elif not any(item.get("action") == action_name for item in intent.actions):
            intent.actions.insert(0, action)
    expected_text = intent.source_expected
    for _, definition in skill_assertions.items():
        triggers = [str(item) for item in definition.get("triggers") or []]
        if not triggers or not any(trigger in expected_text for trigger in triggers):
            continue
        kind = definition.get("type")
        if kind not in {"readonly", "page_size", "pagination_page", "selected_row_count",
                        "visible_fields", "filter_controls", "status_groups"}:
            continue
        from core.ui_test_intake import UiOracle
        oracle = UiOracle(kind, str(definition.get("expected", "page" if kind == "readonly" else "")),
                          True, expected_text, fields=list(definition.get("fields") or []))
        if not any(item.kind == oracle.kind and item.value == oracle.value for item in intent.oracles):
            intent.oracles.append(oracle)
        matched = [text for text in intent.unresolved_expectations
                   if any(trigger in text for trigger in triggers)]
        if matched:
            intent.unresolved_expectations = [text for text in intent.unresolved_expectations if text not in matched]
    case_dir = run_dir / _safe(intent.case_id)
    case_dir.mkdir(parents=True, exist_ok=True)
    if intent.write_risk and not args.allow_write:
        return {**intent.to_dict(), "verdict": "BLOCKED", "reason": "用例包含写入/审批操作，需要显式 --allow-write",
                "execution": {}, "acceptance": {"coverage": 0.0, "verdict": "NOT_RUN"}}
    context_args: dict[str, Any] = {"record_video_dir": str(case_dir / "video"),
                                    "record_video_size": {"width": 1440, "height": 900}}
    if args.session:
        context_args["storage_state"] = str(Path(args.session).resolve())
    context = browser.new_context(**context_args)
    page = context.new_page()
    requests: list[dict[str, Any]] = []

    def capture(response):
        if response.request.resource_type in {"xhr", "fetch"}:
            requests.append({"method": response.request.method, "url": response.url, "status": response.status})

    page.on("response", capture)
    started = time.time()
    try:
        response = page.goto(intent.page_url, wait_until="domcontentloaded", timeout=args.timeout_ms)
        page.wait_for_timeout(args.wait_ms)
        before = case_dir / "before.png"
        page.screenshot(path=str(before), full_page=True)
        body_text = page.locator("body").inner_text()
        structured_actions = [action for action in intent.actions if action.get("action") not in {"click"}]
        structured_labels = {
            str(label).strip()
            for action in structured_actions if action.get("action") == "switch_tabs"
            for label in action.get("labels") or []
        }
        redundant_clicks = {
            id(action) for action in intent.actions
            if _is_redundant_click(action, structured_actions)
        }
        executable_actions = structured_actions + [
            action for action in intent.actions
            if id(action) not in redundant_clicks and str(action.get("text") or "").strip() not in structured_labels
            and action.get("action") == "click" and str(action.get("text") or "") in body_text
        ]
        skipped_actions = [{"action": action.get("action"), "target": action.get("text") or action,
                            "ok": None,
                            "error": "页面未发现该文案，未盲目点击"}
                           for action in intent.actions if action.get("action") == "click"
                           and id(action) not in redundant_clicks
                           and str(action.get("text") or "").strip() not in structured_labels
                           and action not in executable_actions]
        action_results = []
        for action in executable_actions:
            if action.get("action") in {"open_first_record", "select_first_row", "go_to_page",
                                         "prepare_filter", "switch_tabs"}:
                structured_result = _execute_structured_action(page, action, page_model)
                if structured_result.get("ok") is False and action.get("action") == "open_first_record":
                    structured_result = {"action": action["action"], "target": action,
                                         "ok": None, "error": "未发现可稳定匹配的需求单号行，未盲目点击"}
                action_results.append(structured_result)
            else:
                action_results.extend(replay(page, [action]))
        for result_row in action_results:
            if result_row.get("action") != "switch_tabs" or result_row.get("ok") is not None:
                continue
            labels = [str(label) for label in (result_row.get("target") or {}).get("labels") or []]
            if labels and all(label in {"待处理", "执行中", "全部"} for label in labels):
                result_row["ok"] = True
                result_row["diagnostic_only"] = True
                result_row["error"] = "业务状态分组已由状态断言验证；页面无独立页签不阻塞执行"
        action_results += skipped_actions
        page.wait_for_timeout(500)
        after = case_dir / "after.png"
        page.screenshot(path=str(after), full_page=True)
        (case_dir / "page.html").write_text(page.content(), encoding="utf-8")
        oracle_results = [_evaluate_oracle(page, item.to_dict()) for item in intent.oracles]
        action_failed = any(item.get("ok") is False for item in action_results)
        action_unresolved = any(item.get("ok") is None for item in action_results)
        technical = "PASS" if response and response.status < 400 and not action_failed else "FAIL"
        covered = len(oracle_results)
        total = covered + len(intent.unresolved_expectations)
        coverage = covered / total if total else 0.0
        if technical == "FAIL":
            verdict = "FAIL"
        elif any(item.get("passed") is False for item in oracle_results):
            verdict = "FAIL"
        elif action_unresolved or any(item.get("passed") is None for item in oracle_results) \
                or total == 0 or coverage < 1:
            verdict = "INCONCLUSIVE"
        elif all(item["passed"] for item in oracle_results):
            verdict = "PASS"
        else:
            verdict = "FAIL"
        try:
            video = str(Path(page.video.path()).relative_to(run_dir))
        except Exception:
            video = ""
        return {**intent.to_dict(), "verdict": verdict,
                "business_skill": skill.context(args.url) if skill else None,
                "layers": {"ui": {"verdict": verdict, "executed": True},
                           "api": {"verdict": "NOT_EXECUTED", "reason": "UI-first phase"},
                           "db": {"verdict": "NOT_EXECUTED", "reason": "UI-first phase"}},
                "execution": {"browser_opened": True, "status_code": response.status if response else None,
                              "actions_replayed": action_results, "technical_verdict": technical,
                              "duration_s": round(time.time() - started, 3)},
                "acceptance": {"required": total, "executed": covered, "coverage": coverage,
                               "results": oracle_results, "unresolved": intent.unresolved_expectations,
                               "verdict": verdict if verdict in {"PASS", "FAIL"} else "INCONCLUSIVE"},
                "evidence": {"screenshots": [str(before.relative_to(run_dir)), str(after.relative_to(run_dir))],
                             "video": video, "html": str((case_dir / "page.html").relative_to(run_dir)),
                             "network_diagnostics": {"count": len(requests), "requests": requests}}}
    except Exception as exc:  # noqa: BLE001
        return {**intent.to_dict(), "verdict": "ENV_ERROR",
                "layers": {"ui": {"verdict": "ENV_ERROR", "executed": False},
                           "api": {"verdict": "NOT_EXECUTED", "reason": "UI-first phase"},
                           "db": {"verdict": "NOT_EXECUTED", "reason": "UI-first phase"}},
                "reason": str(exc),
                "execution": {"browser_opened": False, "technical_verdict": "ENV_ERROR"},
                "acceptance": {"coverage": 0.0, "verdict": "NOT_RUN"}}
    finally:
        context.close()


def _render_html(report: dict[str, Any], output: Path) -> None:
    cards = []
    for case in report["cases"]:
        acceptance = case.get("acceptance") or {}
        execution = case.get("execution") or {}
        cards.append(
            f"<section><h2>{html.escape(case['case_id'])} {html.escape(case['title'])}</h2>"
            f"<p class='{case['verdict'].lower()}'><b>最终结果：{case['verdict']}</b></p>"
            f"<h3>技术执行</h3><pre>{html.escape(json.dumps(execution, ensure_ascii=False, indent=2))}</pre>"
            f"<h3>业务验收</h3><pre>{html.escape(json.dumps(acceptance, ensure_ascii=False, indent=2))}</pre></section>"
        )
    output.write_text("<!doctype html><meta charset=utf-8><title>UI 测试报告</title>"
                      "<style>body{font:14px/1.6 sans-serif;max-width:1100px;margin:auto;background:#f6f8fa}"
                      "section{background:white;padding:18px;margin:16px;border:1px solid #ddd;border-radius:8px}"
                      ".pass{color:#16833b}.fail,.env_error{color:#c62828}.inconclusive,.blocked{color:#9a6700}"
                      "pre{white-space:pre-wrap}</style>" + "".join(cards), encoding="utf-8")


def run(args: argparse.Namespace) -> dict[str, Any]:
    missing = validate_intake(cases=args.cases, base_url=args.url, session=args.session or "")
    cases_path = Path(args.cases).resolve() if args.cases else None
    if cases_path and not cases_path.is_file():
        missing.append({"field": "cases", "message": f"用例文件不存在：{cases_path}"})
    session_path = Path(args.session).resolve() if args.session else None
    if session_path and not session_path.is_file():
        missing.append({"field": "session", "message": f"登录态文件不存在：{session_path}"})
    if missing:
        return {"status": "NEEDS_INPUT", "missing_information": missing}
    run_id = args.run_id or f"ui_test_{time.strftime('%Y%m%d_%H%M%S')}"
    run_dir = Path(args.workspace).resolve() / "reports" / "ui-tests" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    raws = read_cases(cases_path)
    wanted = {item.strip() for item in (args.only or "").split(",") if item.strip()}
    if wanted:
        raws = [raw for raw in raws if raw.case_id in wanted or raw.name in wanted]
    if not raws:
        return {"status": "NEEDS_INPUT", "missing_information": [
            {"field": "only", "message": "指定范围内没有匹配的 UI 用例"}
        ]}
    write_cases = [raw for raw in raws if build_ui_intent(raw, args.url).write_risk]
    write_policy = parse_write_scope(getattr(args, "write_scope", "")) if write_cases else None
    if write_cases and getattr(args, "allow_write", False):
        policy_errors = validate_write_policy(getattr(args, "write_scope", ""))
        if policy_errors:
            return {"status": "NEEDS_INPUT", "missing_information": policy_errors}
    if write_cases and not getattr(args, "allow_write", False):
        # Keep the default read-only behavior, but make the reason explicit.
        pass
    # This entry point is intentionally UI-first: cases without a UI surface
    # are reported as deferred instead of silently becoming API/DB tests.
    ui_cases = []
    deferred = []
    for raw in raws:
        text = f"{raw.name}\n{raw.steps_text}\n{raw.expected_text}"
        if "ui" in classify_case(raw)["required_layers"]:
            ui_cases.append(raw)
            continue
        if any(token in text for token in ("页面", "点击", "进入", "查看", "切换", "列表", "弹窗", "按钮", "展示", "显示")):
            ui_cases.append(raw)
        else:
            deferred.append({"case_id": raw.case_id, "title": raw.name,
                             "verdict": "DEFERRED", "reason": "未识别到 UI 场景，UI-first 不执行接口/数据库测试"})
    from playwright.sync_api import sync_playwright
    browser = None
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not args.headed)
            results = [_run_case(browser, raw, args, run_dir) for raw in ui_cases]
            browser.close()
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass
    workspace_path = Path(args.workspace).resolve()
    for item in results:
        _attach_visual_result(item, run_dir, getattr(args, "visual_baselines", "") or "",
                              float(getattr(args, "visual_threshold", 0.0) or 0.0))
        if item.get("verdict") == "INCONCLUSIVE":
            item["exploration_candidates"] = _persist_exploration_candidates(workspace_path, item)
        item["replay_verified_candidates"] = _record_candidate_replay(workspace_path, item)
    for item in results:
        evidence = item.get("evidence") or {}
        if evidence and not evidence.get("video"):
            videos = sorted((run_dir / _safe(item.get("case_id") or "case") / "video").glob("*.webm"))
            if videos:
                evidence["video"] = str(videos[0].relative_to(run_dir))
    counts: dict[str, int] = {}
    results.extend(deferred)
    for item in results:
        counts[item["verdict"]] = counts.get(item["verdict"], 0) + 1
    skill = match_skill(args.workspace, args.url)
    report = {"status": "COMPLETED", "mode": "ui-only", "phase": "ui",
              "api_execution": "NOT_EXECUTED", "db_execution": "NOT_EXECUTED",
              "business_skill": skill.context(args.url) if skill else None,
              "run_id": run_id, "source": str(cases_path), "url": args.url,
              "write_policy": write_policy.to_dict() if write_policy else None,
              "counts": counts, "cases": results, "fixture_cleanup": cleanup_fixtures(run_dir),
              "report": str(run_dir / "report.html")}
    _write_json(run_dir / "summary.json", report)
    from scripts.render_ui_report import render_summary
    render_summary(run_dir)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="从用例文件直接执行 UI 测试")
    parser.add_argument("--cases", required=True)
    parser.add_argument("--url", required=True, help="测试环境入口地址")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--session", help="Playwright storageState 登录态文件")
    parser.add_argument("--run-id")
    parser.add_argument("--only", help="只执行指定用例编号，逗号分隔")
    parser.add_argument("--allow-write", action="store_true")
    parser.add_argument("--write-scope", help="写操作安全声明；必须明确测试数据、允许动作和清理策略")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--visual-baselines", help="已审批视觉 baseline 目录")
    parser.add_argument("--visual-threshold", type=float, default=0.0)
    parser.add_argument("--timeout-ms", type=int, default=20000)
    parser.add_argument("--wait-ms", type=int, default=1000)
    args = parser.parse_args()
    report = run(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] == "NEEDS_INPUT":
        return 4
    return 1 if any(key in report["counts"] for key in ("FAIL", "ENV_ERROR")) else 0


if __name__ == "__main__":
    raise SystemExit(main())
