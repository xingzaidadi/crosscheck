from core.soak import run_fault_injection


def test_fault_injection_requires_explicit_recovery():
    result = run_fault_injection(lambda fault: {"recovered": fault in {"timeout", "handler_error"}})
    assert result["passed"] is True
