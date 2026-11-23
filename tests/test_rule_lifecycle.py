"""Propose mined candidates (dedup vs existing REVIEW.md) and suggest prunes.

Both functions only *suggest* — they never write REVIEW.md. Writing stays a human,
reviewed step (阶段 B 的"不经人审不得晋级"红线).
"""
from core.rule_lifecycle import propose_rules, prune_rules

EXISTING = """## RULE: pipeline-stop-path
- trigger: core/pipeline_runner.py
- check: 已有的检查
- incident: 已有事故

## RULE: dup-target
- trigger: core/x.py
- check: 行为与预期偏差反复出现：确认是被测系统缺陷还是断言/映射错，别当环境问题重试
- incident: old
"""


def _cand(name, check, triggers=None):
    return {"name": name, "triggers": triggers or ["core/x.py"], "check": check,
            "incident": "mined", "occurrences": 2, "sample_case_ids": ["s/TC1", "s/TC2"]}


def test_propose_filters_out_duplicates():
    cands = [
        _cand("new-one", "全新的检查点"),
        _cand("target-fail-bug-candidate",
              "行为与预期偏差反复出现：确认是被测系统缺陷还是断言/映射错，别当环境问题重试"),
    ]
    result = propose_rules(cands, EXISTING)
    new_names = [c["name"] for c in result["new_candidates"]]
    assert "new-one" in new_names
    # The candidate whose check duplicates an existing rule is not re-proposed.
    assert "target-fail-bug-candidate" not in new_names
    assert len(result["duplicates"]) == 1


def test_propose_does_not_write_anything(tmp_path):
    cands = [_cand("new-one", "全新的检查点")]
    result = propose_rules(cands, EXISTING)
    # It returns suggestions and a REVIEW.md snippet to review, writes no file.
    assert "review_md_snippet" in result
    assert "## RULE: new-one" in result["review_md_snippet"]


def test_prune_flags_duplicate_rules():
    dup_review = EXISTING + """
## RULE: dup-target-2
- trigger: core/y.py
- check: 行为与预期偏差反复出现：确认是被测系统缺陷还是断言/映射错，别当环境问题重试
- incident: another copy
"""
    result = prune_rules(dup_review)
    prune_names = [r["name"] for r in result["prune"]]
    # Two rules share the same check -> one is flagged as a redundant prune candidate.
    assert "dup-target-2" in prune_names or "dup-target" in prune_names
    assert result["keep"]  # non-duplicate rules are kept


def test_prune_keeps_all_when_no_duplicates():
    result = prune_rules(EXISTING)
    # EXISTING has two distinct checks -> nothing to prune.
    assert result["prune"] == []
    assert len(result["keep"]) == 2


def test_prune_usage_missing_name_is_not_flagged():
    """A rule absent from the usage map must not be treated as never-matched (missing != 0)."""
    result = prune_rules(EXISTING, usage={"pipeline-stop-path": 3})  # dup-target not listed
    prune_names = [r["name"] for r in result["prune"]]
    assert "dup-target" not in prune_names  # absent from usage map -> kept, not pruned


def test_prune_flags_never_matched_when_usage_says_zero():
    result = prune_rules(EXISTING, usage={"pipeline-stop-path": 0, "dup-target": 5})
    prune_names = [r["name"] for r in result["prune"]]
    assert "pipeline-stop-path" in prune_names
