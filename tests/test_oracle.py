from core.oracle import evaluate, evaluate_one, poll


def test_oracles_support_nested_paths_and_operators():
    evidence = {"api": {"data": {"status": "PUBLISHED", "amount": 120}},
                "ui": {"text": "Published strategy"}}
    result = evaluate([
        {"id": "a1", "subject": "api.data.status", "operator": "equals", "expected": "PUBLISHED", "proof": "api"},
        {"id": "a2", "subject": "api.data.amount", "operator": "gte", "expected": 100, "proof": "api"},
        {"id": "a3", "subject": "ui.text", "operator": "contains", "expected": "strategy", "proof": "ui"},
    ], evidence)
    assert result["passed"] is True


def test_missing_not_equals_and_failed_oracle_are_explicit():
    assert evaluate_one({"id": "a", "subject": "api.nope", "operator": "not_equals", "expected": "x"}, {"api": {}})["passed"]
    result = evaluate([{"id": "a", "subject": "api.code", "operator": "equals", "expected": 0}], {"api": {"code": 1}})
    assert result["passed"] is False
    assert result["failed"] == ["a"]


def test_poll_stops_when_until_oracle_passes():
    calls = {"count": 0}

    def evidence():
        calls["count"] += 1
        return {"api": {"status": "READY" if calls["count"] > 1 else "PENDING"}}

    result = poll([{"id": "ready", "subject": "api.status", "operator": "equals", "expected": "READY"}],
                  evidence, until="ready", timeout_s=0.1, interval_s=0.01)
    assert result["passed"] is True
    assert result["until_passed"] is True
