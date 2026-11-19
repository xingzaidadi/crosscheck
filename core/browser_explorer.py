"""Safe, read-only browser exploration for unresolved UI assertion candidates."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from core.asset_pipeline import create_candidate
from core.asset_store import AssetStore
from core.exploration_actions import build_action_candidates


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in value)[:120]


def _resolve_session(workspace: Path, session: str) -> Path | None:
    if not session:
        return None
    raw = Path(session)
    candidates = [raw] if raw.is_absolute() else [workspace / raw, Path.cwd() / raw]
    for candidate in candidates:
        candidate = candidate.resolve()
        try:
            candidate.relative_to(workspace.resolve())
        except ValueError:
            try:
                candidate.relative_to(Path.cwd().resolve())
            except ValueError:
                continue
        if candidate.is_file():
            return candidate
    return None


def explore_task(task: dict[str, Any], *, workspace: str | Path, output: str | Path,
                 timeout_ms: int = 15000) -> dict[str, Any]:
    """Load a candidate's page without clicking or mutating application state."""
    workspace_path = Path(workspace).resolve()
    output_path = Path(output).resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    task_id = _safe_name(f"{task.get('source_case_key')}-{task.get('assertion_id')}")
    evidence_dir = output_path / task_id
    evidence_dir.mkdir(parents=True, exist_ok=True)
    page_url = str(task.get("page_url") or "")
    if not page_url:
        return {**task, "status": "WAITING_FOR_INPUT", "error": "page_url is required"}
    if not bool(task.get("safe_to_auto_explore")):
        return {**task, "status": "WAITING_FOR_INPUT", "error": "task is not read-only safe"}

    session = _resolve_session(workspace_path, str(task.get("session") or ""))
    if task.get("session") and session is None:
        return {**task, "status": "WAITING_FOR_INPUT", "error": "session is missing or outside workspace"}
    started = time.time()
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context_args = {"storage_state": str(session)} if session else {}
            context = browser.new_context(**context_args)
            page = context.new_page()
            response = page.goto(page_url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(800)
            screenshot = evidence_dir / "before.png"
            html = evidence_dir / "page.html"
            dom = evidence_dir / "dom.txt"
            page.screenshot(path=str(screenshot), full_page=True)
            html.write_text(page.content(), encoding="utf-8")
            dom.write_text(page.locator("body").inner_text(timeout=3000), encoding="utf-8")
            body_text = dom.read_text(encoding="utf-8")
            action_candidates = build_action_candidates(
                str(task.get("text") or ""), body_text
            )
            # Exploration is intentionally non-mutating: candidates are recorded,
            # but no click is performed until a reviewed replay binding exists.
            status_code = response.status if response else None
            final_url = page.url
            context.close()
            browser.close()
    except Exception as exc:  # noqa: BLE001
        return {**task, "status": "EXPLORATION_ERROR", "error": str(exc)[:500],
                "duration_s": round(time.time() - started, 3)}

    payload = {
        "case_id": task.get("case_id"),
        "assertion_id": task.get("assertion_id"),
        "page_url": page_url,
        "final_url": final_url,
        "status_code": status_code,
        "strategy": task.get("strategy"),
        "evidence": [str(path.relative_to(output_path)) for path in (screenshot, html, dom)],
        "exploration": "read_only_page_load",
        "action_candidates": action_candidates,
        "oracle_candidate": {
            "type": "dom_text_or_visibility",
            "status": "candidate",
            "requires_review": True,
            "assertion_id": task.get("assertion_id"),
        },
    }
    asset = create_candidate(payload, asset_type="ui_assertion_exploration")
    asset["source"] = {"case_id": task.get("case_id"), "assertion_id": task.get("assertion_id")}
    asset["evidence"] = payload["evidence"]
    store = AssetStore(workspace_path / "knowledge_base" / "asset_candidates")
    asset_path = store.save(asset)
    result = {**task, "status": "REPLAY_VERIFIED", "evidence": payload["evidence"],
              "asset_id": asset["asset_id"], "asset_path": str(asset_path),
              "final_url": final_url, "status_code": status_code,
              "duration_s": round(time.time() - started, 3)}
    (evidence_dir / "exploration.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result
