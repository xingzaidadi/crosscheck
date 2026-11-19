from core.evidence_sufficiency import assess_evidence, infer_objective


def test_ui_and_db_can_prove_file_business_behavior_without_storage_access():
    result = assess_evidence("business_behavior", {"ui", "db"}, assertions_passed=True)
    assert result["verdict"] == "PASS"
    assert result["provider_required"] is False


def test_db_landed_external_result_can_prove_integration_result():
    result = assess_evidence("integration_result", {"api", "db"}, assertions_passed=True)
    assert result["verdict"] == "PASS"


def test_transport_case_still_requires_provider_evidence():
    result = assess_evidence("integration_transport", {"ui", "api", "db"}, assertions_passed=True)
    assert result["verdict"] == "INCONCLUSIVE"
    assert infer_objective({"title": "验证 MQ 消息投递与消费次数"}) == "integration_transport"


def test_technology_name_alone_does_not_force_transport_scope():
    assert infer_objective({"title": "SAP 返回号码在详情页正确展示"}) == "business_behavior"
    assert infer_objective({"title": "通过页面上传并下载 FDS 附件"}) == "business_behavior"
