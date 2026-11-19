from core.business_capabilities import CapabilityPack


def test_capability_pack_requires_explicit_handlers_and_compensation():
    pack = CapabilityPack("demo", "1")
    pack.register("thing.create", lambda **_: {"outputs": {"id": "1"}},
                  compensator=lambda **_: {"status": "compensated"}, evidence=["api.json"])
    assert pack.validate(["thing.create", "thing.approve"]) == ["thing.approve"]
    assert pack.execute("thing.create")["outputs"]["id"] == "1"
    assert pack.compensate("thing.create")["status"] == "compensated"
    assert pack.compensate("thing.approve")["status"] == "manual_required"
