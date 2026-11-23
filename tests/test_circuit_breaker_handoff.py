import hashlib
import json

from core.circuit_breaker import (
    BreakerDecision,
    append_handoff,
    build_handoff,
    read_handoffs,
)


def _decision() -> BreakerDecision:
    return BreakerDecision(
        tripped=True, case_id="TC1", failure_class="TARGET_FAIL",
        attempts=3, threshold=3, reason="repeated 3 times",
    )


def test_build_handoff_contains_core_fields_and_hash():
    packet = build_handoff(
        _decision(),
        run_id="r1",
        triage_bucket="bug_candidate",
        last_verdict="fail",
        last_details=["字段未找到: order_no"],
        evidence_refs=["r1/events.jsonl"],
        suggested_action="human_review_selector_binding",
    )
    assert packet["case_id"] == "TC1"
    assert packet["failure_class"] == "TARGET_FAIL"
    assert packet["attempts"] == 3
    assert packet["threshold"] == 3
    assert packet["triage_bucket"] == "bug_candidate"
    assert packet["last_verdict"] == "fail"
    assert packet["evidence_refs"] == ["r1/events.jsonl"]
    assert packet["content_hash"].startswith("sha256:")


def test_content_hash_is_stable_and_excludes_itself():
    packet = build_handoff(_decision(), run_id="r1", triage_bucket="bug_candidate",
                           last_verdict="fail", last_details=[], evidence_refs=[])
    recomputed = {k: v for k, v in packet.items() if k not in {"content_hash", "at"}}
    expected = "sha256:" + hashlib.sha256(
        json.dumps(recomputed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert packet["content_hash"] == expected


def test_append_handoff_is_append_only_and_readable(tmp_path):
    reports = tmp_path / "reports"
    first = build_handoff(_decision(), run_id="r1", triage_bucket="bug_candidate",
                          last_verdict="fail", last_details=[], evidence_refs=[])
    second = build_handoff(
        BreakerDecision(True, "TC2", "ENV_ERROR", 2, 2, "env repeated"),
        run_id="r2", triage_bucket="environment", last_verdict="env_error",
        last_details=[], evidence_refs=[],
    )
    path = append_handoff(reports, first)
    append_handoff(reports, second)
    assert path.name == "blocked_needs_human.jsonl"
    rows = read_handoffs(reports)
    assert [r["case_id"] for r in rows] == ["TC1", "TC2"]
