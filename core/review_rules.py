"""Diff-triggered reliability checklist, read immutably from the base branch.

The rules that gate a change must live where the change cannot touch them. So the
authoritative REVIEW.md is read from the base branch via ``git show``, never from
the working tree — a change editing REVIEW.md cannot weaken the rules judging it.
(See 《Claude验证方法论-文章精读.md》 §三.6.)
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def _git(repo: str | Path, *args: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(repo), capture_output=True,
            text=True, encoding="utf-8", errors="replace",
        )
    except (FileNotFoundError, NotADirectoryError):
        return 127, ""
    return proc.returncode, proc.stdout


def _is_git_repo(repo: str | Path) -> bool:
    code, out = _git(repo, "rev-parse", "--is-inside-work-tree")
    return code == 0 and out.strip() == "true"


def _ref_exists(repo: str | Path, ref: str) -> bool:
    code, _ = _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    return code == 0


def parse_review_md(text: str) -> list[dict[str, Any]]:
    """Parse REVIEW.md into structured rules (name, triggers, check, incident)."""
    rules: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## RULE:"):
            if current is not None:
                rules.append(current)
            current = {"name": line[len("## RULE:"):].strip(),
                       "triggers": [], "check": "", "incident": ""}
            continue
        if current is None:
            continue
        if line.startswith("- trigger:"):
            value = line[len("- trigger:"):].strip()
            current["triggers"] = [item.strip() for item in value.split(",") if item.strip()]
        elif line.startswith("- check:"):
            current["check"] = line[len("- check:"):].strip()
        elif line.startswith("- incident:"):
            current["incident"] = line[len("- incident:"):].strip()
    if current is not None:
        rules.append(current)
    return rules


def read_base_review(repo: str | Path, *, base_ref: str = "main",
                     path: str = "REVIEW.md") -> dict[str, Any]:
    """Read REVIEW.md from the base branch (not the working tree).

    Returns {"text": str, "source": "base"|"absent"|"bad_ref"|"no_git"}.
    A missing-but-valid base distinguishes from a typo'd ref so a misconfigured
    base_ref is not silently treated as "base has no rules".
    """
    if not _is_git_repo(repo):
        return {"text": "", "source": "no_git"}
    if not _ref_exists(repo, base_ref):
        return {"text": "", "source": "bad_ref"}
    code, out = _git(repo, "show", f"{base_ref}:{path}")
    if code != 0:
        return {"text": "", "source": "absent"}
    return {"text": out, "source": "base"}


def changed_files(repo: str | Path, *, base_ref: str = "main",
                  against_base: bool = False) -> list[str]:
    """Files that constitute the current change, sorted for stable hashing.

    Default: the working-tree change set the author is about to commit —
    uncommitted (staged + unstaged) + untracked. This is "this change", not the
    whole branch divergence from base (which on a long-lived branch drags in
    everything already merged elsewhere).

    against_base=True: the branch's own commits vs base (merge-base...HEAD),
    for reviewing a whole branch/PR.
    """
    if not _is_git_repo(repo):
        return []
    seen: set[str] = set()
    if against_base and _ref_exists(repo, base_ref):
        code, out = _git(repo, "diff", "--name-only", f"{base_ref}...HEAD")
        if code == 0:
            seen.update(line.strip() for line in out.splitlines() if line.strip())
    for args in (("diff", "--name-only", "HEAD"),
                 ("ls-files", "--others", "--exclude-standard")):
        code, out = _git(repo, *args)
        if code != 0:
            continue
        seen.update(line.strip() for line in out.splitlines() if line.strip())
    return sorted(name.replace("\\", "/") for name in seen if name)


def _trigger_matches(trigger: str, path: str) -> bool:
    """Match on whole path segments, not arbitrary substrings.

    A directory trigger ('core/ui/') matches files beneath it; a file trigger
    ('core/quality_gate.py') matches that exact path (optionally with a prefix
    directory), but never 'core/quality_gate_modes.py'.
    """
    if trigger.endswith("/"):
        return path == trigger[:-1] or path.startswith(trigger)
    return path == trigger or path.endswith("/" + trigger)


def match_rules(rules: list[dict[str, Any]], changed: list[str]) -> list[dict[str, Any]]:
    """Return rules whose any trigger matches any changed file path (segment-aware)."""
    normalized = [c.replace("\\", "/") for c in changed]
    matched: list[dict[str, Any]] = []
    for rule in rules:
        if any(_trigger_matches(trigger, path)
               for trigger in rule["triggers"] for path in normalized):
            matched.append(rule)
    return matched
