"""Bounded recovery strategies for semantic UI actions."""
from __future__ import annotations

import re
from typing import Callable


def locator_candidates(page, label: str):
    escaped = re.compile(re.escape(label), re.I)
    candidates = [
        ("button_exact", page.get_by_role("button", name=label, exact=True)),
        ("link_exact", page.get_by_role("link", name=label, exact=True)),
        ("text_exact", page.get_by_text(label, exact=True)),
        ("button_fuzzy", page.get_by_role("button", name=escaped)),
        ("link_fuzzy", page.get_by_role("link", name=escaped)),
        ("text_fuzzy", page.get_by_text(label, exact=False)),
        ("title_or_aria", page.locator(f'[aria-label*="{label}"], [title*="{label}"]')),
    ]
    for index, frame in enumerate(getattr(page, "frames", [])[1:], start=1):
        try:
            candidates.extend([
                (f"frame_{index}_button", frame.get_by_role("button", name=escaped)),
                (f"frame_{index}_link", frame.get_by_role("link", name=escaped)),
                (f"frame_{index}_text", frame.get_by_text(label, exact=False)),
            ])
        except Exception:
            continue
    return candidates


def recover_and_click(page, label: str, *, attempts: int = 3,
                      record: Callable[[dict], None] | None = None) -> dict:
    events: list[dict] = []
    for strategy, locator in locator_candidates(page, label):
        if len(events) >= attempts * 3:
            break
        event = {"strategy": strategy, "target": label, "ok": False}
        try:
            candidate = locator.first
            if candidate.count() == 0:
                event["reason"] = "not_found"
            else:
                candidate.scroll_into_view_if_needed(timeout=1200)
                candidate.click(timeout=3000)
                event["ok"] = True
                events.append(event)
                if record:
                    record(event)
                return {"ok": True, "strategy": strategy, "events": events}
        except Exception as exc:
            event["reason"] = str(exc)[:240]
            if "intercepts pointer" in str(exc).lower() or "not visible" in str(exc).lower():
                try:
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(150)
                    event["recovery"] = "dismiss_overlay_with_escape"
                except Exception:
                    pass
        events.append(event)
        if record:
            record(event)
    return {"ok": False, "strategy": "exhausted", "events": events,
            "error": f"unable to locate clickable target: {label}"}
