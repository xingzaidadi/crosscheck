from core.write_policy import parse_write_scope, validate_write_policy


def test_write_policy_requires_bounded_non_production_contract():
    assert validate_write_policy("")
    assert validate_write_policy("environment=production; marker=AUTO; actions=create; cleanup=delete")
    assert validate_write_policy("environment=test; marker=AUTO_2026; actions=create,submit; cleanup=delete") == []
    policy = parse_write_scope("environment=test; marker=AUTO_2026; actions=create,submit; cleanup=delete")
    assert policy.allowed_actions == ("create", "submit")

