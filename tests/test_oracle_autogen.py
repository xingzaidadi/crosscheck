"""业务 Oracle 自动生成器:正向抽取 + 置信度 + 零业务 + 与 oracle.py 端到端。

跑:python tests/test_oracle_autogen.py  或  pytest tests/test_oracle_autogen.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.oracle import evaluate  # noqa: E402
from core.oracle_autogen import (  # noqa: E402
    HIGH_CONFIDENCE,
    LOW_CONFIDENCE,
    generate,
    score,
    summarize,
)

_RULES = {"patterns": [
    {"match": r"至少(\d+)条|存在记录", "layer": "api", "operator": "gte",
     "subject_hint": "data.total,data.records", "expected_from": "group1"}]}
_SAMPLE = {"response_json": {"code": "0", "data": {"total": 3, "records": [{"id": 1}]}}}


def test_score_is_explainable_additive():
    assert score(pattern_hit=True, subject_found=True, expected_known=True,
                 mapping_supported=True) == 1.0
    assert score(pattern_hit=True, subject_found=False, expected_known=False,
                 mapping_supported=False) == 0.4
    assert score(pattern_hit=False, subject_found=False, expected_known=False,
                 mapping_supported=False) == 0.0


def test_generate_positive_api_candidate_and_full_confidence():
    cands = generate("列表至少1条", api_sample=_SAMPLE, rules=_RULES,
                     mapped_fields={"total"}, sample_ref="captures/x.json")
    assert len(cands) == 1
    c = cands[0]
    assert c["status"] == "candidate"            # 永远 candidate,不自动过闸
    assert c["subject"] == "data.total" and c["operator"] == "gte" and c["expected"] == 1
    assert c["confidence"] == 1.0
    assert c["evidence_refs"] == ["captures/x.json#data.total"]


def test_candidate_is_evaluable_by_oracle_py():
    cands = generate("列表至少1条", api_sample=_SAMPLE, rules=_RULES)
    oracles = [{"id": c["id"], "subject": c["subject"], "operator": c["operator"],
                "expected": c["expected"]} for c in cands]
    assert evaluate(oracles, {"data": {"total": 3}})["passed"] is True
    assert evaluate(oracles, {"data": {"total": 0}})["passed"] is False


def test_missing_subject_lowers_confidence_and_notes():
    cands = generate("列表至少1条", api_sample={"response_json": {"data": {}}}, rules=_RULES)
    c = cands[0]
    assert c["confidence"] < HIGH_CONFIDENCE
    assert any("subject" in note for note in c.get("notes", []))
    assert c["evidence_refs"] == []              # 无证据不伪造 ref


def test_db_constraints_yield_existence_and_enum_oracles():
    dbc = {"status_code": {"required": True, "enum": ["A", "B"], "type": "enum"},
           "name": {"required": True, "enum": [], "type": "varchar"},
           "note": {"required": False}}
    cands = generate("", db_constraints=dbc, rules={"patterns": []})
    by_subject = {c["subject"]: c for c in cands}
    assert by_subject["status_code"]["operator"] == "in"
    assert by_subject["status_code"]["expected"] == ["A", "B"]
    assert by_subject["name"]["operator"] == "exists"
    assert "note" not in by_subject               # 非 required 不产


def test_bad_regex_rule_does_not_crash():
    assert generate("x", rules={"patterns": [{"match": "*broken", "layer": "api",
                                              "operator": "exists"}]}) == []


def test_unsupported_operator_is_skipped():
    rules = {"patterns": [{"match": "显示", "layer": "api", "operator": "frobnicate",
                           "subject_hint": "data.x"}]}
    assert generate("显示", api_sample=_SAMPLE, rules=rules) == []


def test_never_sets_human_verified():
    cands = generate("列表至少1条", api_sample=_SAMPLE, rules=_RULES)
    for c in cands:
        assert c["status"] == "candidate"
        assert "verify_status" not in c and "human_verified" not in str(c)


def test_summarize_buckets():
    cands = generate("列表至少1条", api_sample=_SAMPLE, rules=_RULES, mapped_fields={"total"})
    cands += generate("", db_constraints={"n": {"required": True, "enum": []}},
                      rules={"patterns": []})
    buckets = summarize(cands)
    assert buckets["total"] == len(cands)
    assert all(c["confidence"] >= HIGH_CONFIDENCE for c in buckets["high"])
    assert all(c["confidence"] < LOW_CONFIDENCE for c in buckets["low"])


def main() -> None:
    test_score_is_explainable_additive()
    test_generate_positive_api_candidate_and_full_confidence()
    test_candidate_is_evaluable_by_oracle_py()
    test_missing_subject_lowers_confidence_and_notes()
    test_db_constraints_yield_existence_and_enum_oracles()
    test_bad_regex_rule_does_not_crash()
    test_unsupported_operator_is_skipped()
    test_never_sets_human_verified()
    test_summarize_buckets()
    print("test_oracle_autogen ✅ 全部通过")


if __name__ == "__main__":
    main()
