from scripts.promote_reviewed_bindings import case_key


def test_case_key_normalizes_ui_suffix(tmp_path):
    assert case_key({"case_id": "TC117-UI"}, tmp_path / "x.yaml") == "TC117"
