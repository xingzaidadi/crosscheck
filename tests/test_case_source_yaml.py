from core.case_source import read_cases


def test_yaml_cases_are_supported(tmp_path):
    path = tmp_path / "cases.yaml"
    path.write_text("cases:\n  - name: TC01\n    steps_text: 查询\n    expected_text: 显示结果\n", encoding="utf-8")
    cases = read_cases(path)
    assert len(cases) == 1
    assert cases[0].case_id == "TC01"


def test_yaml_case_keeps_role_data_and_risk(tmp_path):
    path = tmp_path / "cases.yaml"
    path.write_text("cases:\n  - id: TC02\n    title: 审批\n    role: 经理\n    test_data: AUTOTEST_001\n    risk: 越权\n", encoding="utf-8")
    case = read_cases(path)[0]
    assert case.name == "TC02 审批"
    assert (case.role, case.test_data, case.risk) == ("经理", "AUTOTEST_001", "越权")
