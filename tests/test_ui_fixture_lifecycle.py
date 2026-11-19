from pathlib import Path

from core.ui_fixture_lifecycle import cleanup_fixtures, provision_fixture


def test_fixture_lifecycle_records_cleanup_and_residue(tmp_path):
    record = provision_fixture({"kind": "csv", "marker": "AUTO-1", "rows": 2}, tmp_path)
    assert Path(record["path"]).is_file()
    result = cleanup_fixtures(tmp_path)
    assert result == {"cleaned": ["AUTO-1"], "failed": [], "residue": False}
    assert not Path(record["path"]).exists()

