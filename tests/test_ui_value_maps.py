from core.ui_verifier import verify_display


def test_ui_value_maps_normalize_api_enums():
    result = verify_display(
        [{"状态": "受理中"}],
        {"data": {"records": [{"status": "ACCEPTING"}]}},
        {"dom_to_api": {"状态": "status"}, "api_rows_path": "data.records",
         "value_maps": {"状态": {"ACCEPTING": "受理中"}}},
    )
    assert result.consistent
    assert result.pairs[0]["normalized_api"] == "受理中"
