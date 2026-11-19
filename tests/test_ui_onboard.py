import json
from pathlib import Path

import yaml

from scripts.ui_onboard import onboard


def test_ui_onboard_creates_profile_model_and_intake(tmp_path):
    cases = tmp_path / "cases.csv"
    cases.write_text("case_id,name,steps,expected\nTC1,查询,打开页面,显示列表\n", encoding="utf-8")
    result = onboard(workspace=str(tmp_path / "ws"), system="Demo System",
                     url="https://example.test/app", cases=str(cases), roles=["operator"])
    profile = yaml.safe_load(Path(result["profile"]).read_text(encoding="utf-8"))
    intake = json.loads(Path(result["intake"]).read_text(encoding="utf-8"))
    assert profile["site"] == "demo-system"
    assert Path(result["application_model"]).is_file()
    assert intake["status"] == "READY_FOR_EXPLORATION"

