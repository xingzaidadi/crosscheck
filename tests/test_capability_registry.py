from pathlib import Path

from core.arsenal import load_capabilities, validate_capability_registry


def test_capability_registry_requires_evidence_compensation_and_execution(tmp_path: Path):
    path = tmp_path / "capabilities.yaml"
    path.write_text("""
capabilities:
  - capability_id: thing.create
    version: '1'
    kind: api
    provides: {id: thing.id}
    effects: {mutates: true}
    environment: test
""", encoding="utf-8")
    errors = validate_capability_registry(load_capabilities(path), environment="test")
    assert any("evidence" in error for error in errors)
    assert any("compensation" in error for error in errors)
    assert any("execution" in error for error in errors)
