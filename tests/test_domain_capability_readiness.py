from core.domain_capability_readiness import assess_domain_capabilities, required_actions


def _pack(tmp_path, kinds):
    rows = []
    for index, kind in enumerate(kinds):
        rows.append(
            "  - capability_id: cap.%d\n    version: '1.0'\n    kind: %s\n"
            "    environment: test\n    owner: qa\n    state: healthy\n"
            "    provides:\n      object_type: demand\n"
            "    effects:\n      mutates: false\n"
            "    execution:\n      mode: api\n      route_ref: r%d\n"
            "    evidence: [api_response]\n" % (index, kind, index)
        )
    path = tmp_path / "capabilities.yaml"
    path.write_text("schema_version: 1\ncapabilities:\n" + "".join(rows), encoding="utf-8")
    return path


def test_required_actions_are_classified_from_precondition_text():
    actions = required_actions({"data": {"preconditions_text": "已创建需求单并提交审批，列表展示"}})
    assert "create" in actions
    assert "transition" in actions
    assert "query" in actions


def test_missing_capability_kind_is_reported_as_gap(tmp_path):
    registry = _pack(tmp_path, ["find"])
    report = assess_domain_capabilities(
        [{"case_id": "s/TC1", "data": {"preconditions_text": "已创建并提交需求单"}}],
        registry_path=registry,
    )
    assert report["capability_pack_valid"] is True
    assert "create" in report["missing_action_kinds"]
    assert "transition" in report["missing_action_kinds"]
    assert report["coverage"] < 1.0


def test_full_capability_pack_covers_actions(tmp_path):
    registry = _pack(tmp_path, ["create", "transition", "find", "compensate"])
    report = assess_domain_capabilities(
        [{"case_id": "s/TC1", "data": {"preconditions_text": "创建需求、提交审批、查询列表、清理数据"}}],
        registry_path=registry,
    )
    assert report["coverage"] == 1.0
    assert report["missing_action_kinds"] == []


def test_missing_pack_reports_unavailable(tmp_path):
    report = assess_domain_capabilities(
        [{"case_id": "s/TC1", "data": {"preconditions_text": "创建需求单"}}],
        registry_path=tmp_path / "none.yaml",
    )
    assert report["capability_pack_available"] is False
    assert report["coverage"] == 0.0
    assert "create" in report["missing_action_kinds"]
