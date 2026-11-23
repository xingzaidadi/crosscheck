"""Diff-triggered review gate: match base-branch rules against the current change."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from core.review_rules import (
    changed_files,
    match_rules,
    parse_review_md,
    read_base_review,
)


def build_review_gate(repo: str | Path, *, base_ref: str = "main") -> dict[str, Any]:
    """Read the immutable base-branch REVIEW.md, match it against the current diff.

    Output is machine-readable (matched_rules) plus human-readable next_actions that
    carry each rule's check and incident, so a reviewer need not reverse-engineer the
    diff. (See 《Claude验证方法论-文章精读.md》 §三.3/§三.6.)
    """
    base = read_base_review(repo, base_ref=base_ref)
    rules = parse_review_md(base["text"]) if base["text"] else []
    changed = changed_files(repo, base_ref=base_ref)
    matched = match_rules(rules, changed)
    warnings: list[str] = []
    if base["source"] == "absent":
        warnings.append(f"基线分支 {base_ref} 无 REVIEW.md，规则未生效——空清单不代表安全（首个引入 REVIEW.md 的改动合入后生效）")
    elif base["source"] == "bad_ref":
        warnings.append(f"基线 ref '{base_ref}' 不存在，无法读取规则——请检查 --base-ref")
    elif base["source"] == "no_git":
        warnings.append("非 git 仓库，无法读取基线规则")
    report: dict[str, Any] = {
        "schema_version": 1,
        "base_ref": base_ref,
        "rules_source": base["source"],
        "rules_active": base["source"] == "base",
        "warnings": warnings,
        "changed_files": changed,
        "matched_rules": matched,
        "next_actions": [f"[{r['name']}] {r['check']}（因: {r['incident']}）" for r in matched],
    }
    hashable = {k: v for k, v in report.items() if k != "content_hash"}
    digest = hashlib.sha256(
        json.dumps(hashable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    report["content_hash"] = f"sha256:{digest}"
    return report


def write_review_gate(report: dict[str, Any], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
    return path
