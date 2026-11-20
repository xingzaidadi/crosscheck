from core.ui_agent.acceptance import evaluate_real_acceptance


def test_real_acceptance_reports_operational_metrics():
    sample = {"status": "PASSED", "plan": {"unresolved_expectations": []},
              "execution": {"actions": []}, "human_intervention": False}
    result = evaluate_real_acceptance([sample] * 10)
    assert result["status"] == "PASSED"
    assert result["metrics"]["first_pass_rate"] == 1.0
