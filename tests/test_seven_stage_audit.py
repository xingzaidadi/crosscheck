from pathlib import Path


def test_seven_stage_audit_script_is_present():
    assert Path("scripts/audit_seven_stage_plan.py").is_file()
