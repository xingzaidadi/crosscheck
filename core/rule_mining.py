"""Mine recurring failure patterns from run evidence into REVIEW.md rule candidates.

Per the Claude Code team's methodology (《Claude验证方法论-文章精读.md》 §三.9): only a
pattern seen at least twice qualifies as a rule candidate; candidates are *proposed*,
never auto-written into REVIEW.md (human approval required). This closes the loop by
turning real misses into diff-triggered rules instead of hand-writing them.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core.interfaces import Verdict
from core.triage import classify
from core.soak_report import _load


# Mask tokens that look like ids/numbers/codes (contain a digit, or are long hex-ish),
# so concrete values collapse — but ordinary English words are kept so distinct failures
# don't all degrade to a single "X".
_IDLIKE = re.compile(r"\b(?=\w*\d)[A-Za-z0-9_–\-]{2,}\b")


def normalize_failure(details: list[str]) -> str:
    """Deterministic failure skeleton, computed per-detail then combined.

    Each detail's structural head (text before the first colon) is kept; the concrete
    value after the colon is dropped, and id/number-like tokens are masked. All segments
    are kept (sorted) so multiple distinct signals don't collapse to only the first.
    """
    segments: list[str] = []
    for detail in details or []:
        text = str(detail).strip()
        if not text:
            continue
        head = re.split(r"[:：]", text, maxsplit=1)[0]
        head = _IDLIKE.sub("X", head)
        head = re.sub(r"\s+", " ", head).strip()
        if head and head != "X":
            segments.append(head)
    return " | ".join(sorted(set(segments)))


def _bucket_for(verdict: str, details: list[str]) -> str:
    try:
        v = Verdict(verdict)
    except ValueError:
        v = Verdict.FAIL
    return classify(v, details).get("bucket", "unknown")


_CHECK_BY_BUCKET = {
    "bug_candidate": "行为与预期偏差反复出现：确认是被测系统缺陷还是断言/映射错，别当环境问题重试",
    "modeling": "用例/规格配置反复对不上：检查断言字段、request 映射、SQL 是否仍准确",
    "environment": "环境/登录/连接反复失败：先修环境或凭据，不要计入功能失败",
}


def _candidate(key: tuple[str, str], occ: list[dict[str, Any]]) -> dict[str, Any]:
    failure_class, skeleton = key
    # Bucket by majority vote (stable) rather than first-seen.
    buckets = [o["bucket"] for o in occ]
    bucket = max(set(buckets), key=buckets.count)
    sample_cases = sorted({o["case_id"] for o in occ if o.get("case_id")})
    distinct = len({(o.get("case_id"), o.get("run_id")) for o in occ})
    name = re.sub(r"[^a-z0-9]+", "-", f"{failure_class}-{bucket}".lower()).strip("-")
    return {
        "name": name,
        "triggers": [],  # human fills the code area this failure maps to
        "check": _CHECK_BY_BUCKET.get(bucket, f"反复出现的 {failure_class} 失败，需人工确认根因"),
        "incident": f"{failure_class} 在 {len(sample_cases)} 个用例反复出现（样本: {', '.join(sample_cases[:3])}）；失败骨架: {skeleton[:80]}",
        "failure_class": failure_class,
        "bucket": bucket,
        "occurrences": distinct,
        "sample_case_ids": sample_cases,
    }


def mine_candidates(runs_root: str | Path, *, handoffs: list[dict[str, Any]] | None = None,
                    min_occurrences: int = 2) -> list[dict[str, Any]]:
    """Cluster recurring failures (summaries + breaker handoffs) into rule candidates.

    A pattern qualifies only when it recurs across at least ``min_occurrences`` DISTINCT
    cases — a single flaky case failing repeatedly does not reach the threshold.
    """
    clusters: dict[tuple[str, str], list[dict[str, Any]]] = {}

    def _add(case_id: str, run_id: str, verdict: str, failure_class: str, details: list[str]):
        skeleton = normalize_failure(details)
        if not skeleton:
            return
        bucket = _bucket_for(verdict, details)
        # Only functional-signal failures (bug_candidate/modeling) seed rules.
        if bucket not in ("modeling", "bug_candidate"):
            return
        clusters.setdefault((failure_class or "UNKNOWN", skeleton), []).append(
            {"case_id": case_id, "run_id": run_id, "bucket": bucket})

    root = Path(runs_root)
    if root.exists():
        for summary_path in sorted(root.glob("*/summary.json")):
            data = _load(summary_path)
            if not data:
                continue
            run_id = str(data.get("run_id") or summary_path.parent.name)
            for case in data.get("cases", []):
                verdict = str(case.get("verdict") or "")
                if verdict == "pass":
                    continue
                _add(str(case.get("case_id") or ""), run_id, verdict,
                     str(case.get("failure_class") or ""), list(case.get("details") or []))

    for packet in handoffs or []:
        _add(str(packet.get("case_id") or ""), str(packet.get("run_id") or "handoff"),
             str(packet.get("last_verdict") or "fail"),
             str(packet.get("failure_class") or ""),
             list(packet.get("last_details") or packet.get("details") or []))

    candidates = [_candidate(key, occ) for key, occ in clusters.items()
                  if len({(o.get("case_id"), o.get("run_id")) for o in occ}) >= min_occurrences
                  and len({o.get("case_id") for o in occ}) >= 2]
    candidates.sort(key=lambda c: c["occurrences"], reverse=True)
    return candidates
