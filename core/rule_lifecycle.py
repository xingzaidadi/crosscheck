"""Propose mined rule candidates (dedup vs existing) and suggest prunes — suggest only.

Neither function writes REVIEW.md. Proposing/pruning stays a reviewed, human step,
preserving the "不经人审不得晋级" and base-branch-immutability guarantees.
"""
from __future__ import annotations

from typing import Any

from core.review_rules import parse_review_md


def _rule_to_md(rule: dict[str, Any]) -> str:
    triggers = ", ".join(rule.get("triggers") or []) or "TODO_填写改动域"
    return (f"## RULE: {rule['name']}\n"
            f"- trigger: {triggers}\n"
            f"- check: {rule.get('check', '')}\n"
            f"- incident: {rule.get('incident', '')}\n")


def propose_rules(candidates: list[dict[str, Any]], review_text: str) -> dict[str, Any]:
    """Filter candidates already covered by an existing rule (same check); suggest the rest.

    Does NOT write REVIEW.md — returns new_candidates, duplicates and a snippet to review.
    """
    existing_checks = {r["check"].strip() for r in parse_review_md(review_text) if r.get("check")}
    new_candidates: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    for cand in candidates:
        if cand.get("check", "").strip() in existing_checks:
            duplicates.append(cand)
        else:
            new_candidates.append(cand)
    snippet = "\n".join(_rule_to_md(c) for c in new_candidates)
    return {
        "new_candidates": new_candidates,
        "duplicates": duplicates,
        "review_md_snippet": snippet,
    }


def prune_rules(review_text: str, *, usage: dict[str, int] | None = None) -> dict[str, Any]:
    """Suggest rules to prune: redundant (same check as another rule), or (optional)
    never-hit when a usage map is given. Does NOT delete — returns keep/prune suggestions.

    Among rules sharing a check, the one with the most complete incident is kept (a proxy
    for the hand-curated / authoritative rule), not merely the first seen.
    """
    rules = parse_review_md(review_text)
    # Group by check to pick the keeper per duplicate group deterministically.
    by_check: dict[str, list[dict[str, Any]]] = {}
    order: list[dict[str, Any]] = []
    for rule in rules:
        check = (rule.get("check") or "").strip()
        order.append(rule)
        if check:
            by_check.setdefault(check, []).append(rule)
    keepers = set()
    for check, group in by_check.items():
        best = max(group, key=lambda r: len(r.get("incident") or ""))
        keepers.add(id(best))

    keep: list[dict[str, Any]] = []
    prune: list[dict[str, Any]] = []
    for rule in order:
        check = (rule.get("check") or "").strip()
        if check and id(rule) not in keepers:
            prune.append({**rule, "prune_reason": "duplicate_check"})
            continue
        if usage is not None and rule["name"] in usage and usage.get(rule["name"], 0) == 0:
            # Only flag never-matched when the usage map actually covers this rule.
            prune.append({**rule, "prune_reason": "never_matched"})
            continue
        keep.append(rule)
    return {"keep": keep, "prune": prune}
