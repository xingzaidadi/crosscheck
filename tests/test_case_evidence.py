import json

from core.case_evidence import ingest_sources


def test_source_ingestion_is_read_only_and_classifies_material(tmp_path):
    source = tmp_path / "schema.sql"
    source.write_text("CREATE TABLE orders (status varchar(20)); password=super-secret", encoding="utf-8")
    target = tmp_path / "manifest.json"
    result = ingest_sources([str(source)], target)
    assert result["source_count"] == 1
    assert "database" in result["sources"][0]["signals"]
    assert "super-secret" not in result["sources"][0]["excerpt"]
    assert json.loads(target.read_text(encoding="utf-8"))["source_count"] == 1
