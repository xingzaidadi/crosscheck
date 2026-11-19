import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.arsenal import plan_dependencies


def test_missing_capability_is_a_plan_error_not_an_execution_attempt():
    with pytest.raises(ValueError, match="no healthy capability"):
        plan_dependencies({"case_id": "case-1", "action": {"capability": "missing.action"}},
                          [], environment="test", run_id="run-1")


if __name__ == "__main__":
    raise SystemExit(__import__("pytest").main([__file__, "-q"]))
