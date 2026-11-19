from core.g5_acceptance import run_g5_acceptance


def test_g5_acceptance_matrix_passes(tmp_path):
    result = run_g5_acceptance(repetitions=3)
    assert result["passed"] is True
    assert result["soak"]["passed"] is True
    assert result["fault_injection"]["passed"] is True
    assert result["idempotency"]["passed"] is True
