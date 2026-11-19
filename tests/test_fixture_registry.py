from core.fixture_registry import fixture_for_case, registry_summary


def test_fixture_registry_is_explicit_and_auditable():
    registry = {"fixtures": {"to_accept": {"verified": True, "case_keys": ["TC01"]}}}
    assert fixture_for_case(registry, "TC01")["name"] == "to_accept"
    assert registry_summary(registry) == {"total": 1, "verified": 1, "case_bindings": 1, "unverified": []}
