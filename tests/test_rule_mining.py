"""Mine recurring failure patterns from run evidence into REVIEW.md rule candidates."""
import json

from core.rule_mining import mine_candidates, normalize_failure


def _write_summary(root, run_id, cases):
    path = root / run_id
    path.mkdir(parents=True)
    (path / "summary.json").write_text(json.dumps({"run_id": run_id, "cases": cases}),
                                       encoding="utf-8")


def test_recurring_failure_becomes_candidate(tmp_path):
    runs = tmp_path / "runs"
    # Same failure shape in two different cases -> qualifies (>=2 occurrences).
    _write_summary(runs, "r1", [
        {"case_id": "s/TC1", "verdict": "fail", "failure_class": "TARGET_FAIL",
         "details": ["字段未找到: order_no"]},
    ])
    _write_summary(runs, "r2", [
        {"case_id": "s/TC2", "verdict": "fail", "failure_class": "TARGET_FAIL",
         "details": ["字段未找到: amount"]},
    ])
    cands = mine_candidates(runs, handoffs=[], min_occurrences=2)
    assert len(cands) == 1
    c = cands[0]
    assert c["occurrences"] == 2
    assert set(c["sample_case_ids"]) == {"s/TC1", "s/TC2"}
    assert c["bucket"] in ("bug_candidate", "modeling")
    assert c["check"]           # a human-readable check description
    assert "name" in c and "triggers" in c and "incident" in c


def test_single_occurrence_is_not_proposed(tmp_path):
    runs = tmp_path / "runs"
    _write_summary(runs, "r1", [
        {"case_id": "s/TC1", "verdict": "fail", "failure_class": "TARGET_FAIL",
         "details": ["字段未找到: order_no"]},
    ])
    cands = mine_candidates(runs, handoffs=[], min_occurrences=2)
    assert cands == []  # one occurrence must not create a rule (avoids single-blip noise)


def test_same_case_repeated_does_not_reach_threshold(tmp_path):
    """A single flaky case failing twice (same run, or across runs) must NOT qualify —
    the threshold is distinct cases, not raw failure count."""
    runs = tmp_path / "runs"
    _write_summary(runs, "r1", [
        {"case_id": "s/TC1", "verdict": "fail", "failure_class": "TARGET_FAIL",
         "details": ["字段未找到: a"]},
        {"case_id": "s/TC1", "verdict": "fail", "failure_class": "TARGET_FAIL",
         "details": ["字段未找到: b"]},
    ])
    _write_summary(runs, "r2", [
        {"case_id": "s/TC1", "verdict": "fail", "failure_class": "TARGET_FAIL",
         "details": ["字段未找到: c"]},
    ])
    assert mine_candidates(runs, handoffs=[], min_occurrences=2) == []


def test_normalize_keeps_all_detail_segments():
    """Multiple details must not collapse to only the first segment."""
    multi = normalize_failure(["字段未找到: order_no", "字段不一致: amount"])
    first_only = normalize_failure(["字段未找到: order_no"])
    assert multi != first_only  # the second signal must still influence the skeleton
    assert "不一致" in multi


def test_normalize_does_not_overmerge_distinct_english_failures():
    a = normalize_failure(["order_no not found"])
    b = normalize_failure(["payment gateway timeout"])
    assert a != b  # two unrelated english failures must not both become "X"


def test_blocked_verdict_not_misclassified_as_bug(tmp_path):
    """A blocked failure whose details contain a bug keyword must not be mined as a bug rule."""
    runs = tmp_path / "runs"
    _write_summary(runs, "r1", [
        {"case_id": "s/TC1", "verdict": "blocked", "failure_class": "ENV_ERROR",
         "details": ["只读"]},
    ])
    _write_summary(runs, "r2", [
        {"case_id": "s/TC2", "verdict": "blocked", "failure_class": "ENV_ERROR",
         "details": ["只读"]},
    ])
    # blocked is an environment/non-functional signal; it must not seed a bug_candidate rule.
    cands = mine_candidates(runs, handoffs=[], min_occurrences=2)
    assert all(c["bucket"] != "bug_candidate" for c in cands)


def test_passing_runs_produce_no_candidates(tmp_path):
    runs = tmp_path / "runs"
    _write_summary(runs, "r1", [{"case_id": "s/TC1", "verdict": "pass", "failure_class": "", "details": []}])
    _write_summary(runs, "r2", [{"case_id": "s/TC2", "verdict": "pass", "failure_class": "", "details": []}])
    assert mine_candidates(runs, handoffs=[], min_occurrences=2) == []


def test_normalize_failure_collapses_distinct_values():
    # Different concrete values should normalize to the same skeleton so they cluster.
    a = normalize_failure(["字段未找到: order_no"])
    b = normalize_failure(["字段未找到: amount_123"])
    assert a == b and a != ""


def test_handoffs_count_toward_occurrences(tmp_path):
    runs = tmp_path / "runs"
    _write_summary(runs, "r1", [
        {"case_id": "s/TC1", "verdict": "fail", "failure_class": "TARGET_FAIL",
         "details": ["计算不变量不符: 余额"]},
    ])
    handoffs = [{"case_id": "s/TC9", "failure_class": "TARGET_FAIL",
                 "last_details": ["计算不变量不符: 总额"]}]
    cands = mine_candidates(runs, handoffs=handoffs, min_occurrences=2)
    assert len(cands) == 1
    assert cands[0]["occurrences"] == 2
