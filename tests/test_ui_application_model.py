import pytest

from core.ui_application_model import load_model, seed_model, validate_model, write_model


def test_application_model_round_trip(tmp_path):
    model = seed_model(system="Demo", base_url="https://example.test/app", roles=["operator"])
    path = write_model(model, tmp_path / "demo.yaml")
    loaded = load_model(path)
    assert loaded["pages"]["home"]["roles"] == ["operator"]
    assert validate_model(loaded) == []


def test_application_model_rejects_cross_host_entry():
    model = seed_model(system="Demo", base_url="https://example.test")
    model["pages"]["home"]["entry"] = "https://evil.test"
    assert validate_model(model)[0]["field"] == "pages.home.entry"


def test_application_model_requires_http_url():
    with pytest.raises(ValueError):
        seed_model(system="Demo", base_url="file:///tmp/demo")

