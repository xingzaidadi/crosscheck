from core.maturity_acceptance import evaluate_maturity


def test_four_phase_acceptance_reaches_over_ninety():
    samples = [{
        "status": "PASSED",
        "plan": {"plan_id": f"NL-{index}"},
        "execution": {"recovery_events": [], "actions": []},
        "hardening": {"status": "PROVISIONAL"},
    } for index in range(100)]
    report = evaluate_maturity(samples)
    assert report["status"] == "PASSED"
    assert report["score"] >= 90
    assert {gate["phase"] for gate in report["gates"]} == {
        "1-natural-language", "2-autonomous-exploration", "2-recovery", "3-hardening", "4-safety"
    }
