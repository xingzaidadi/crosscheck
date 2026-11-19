import pytest

from core.real_capability_pack import RealBinding, build_real_pack


def test_real_pack_delegates_authenticated_request_and_compensation():
    calls = []

    def request(method, path, payload):
        calls.append((method, path, payload))
        return {"outputs": {"status": "submitted"}}

    def compensate(capability, path, payload):
        return {"compensated": capability, "path": path}

    pack = build_real_pack(
        "ebuy-demand", "1", [
            RealBinding("requirement.submit", "POST", "/demand/api/demand/submit",
                        mutates=True, idempotent=True, compensate_with="requirement.cancel",
                        evidence=("api",)),
        ], request=request, compensate=compensate,
    )
    result = pack.execute("requirement.submit", inputs={"id": "REQ1"}, context={"site": "ebuy-demand"})
    assert result["outputs"]["status"] == "submitted"
    assert calls[0][0:2] == ("POST", "/demand/api/demand/submit")
    assert pack.compensate("requirement.submit")["compensated"] == "requirement.cancel"


def test_mutating_binding_requires_idempotency_and_compensation():
    binding = RealBinding("requirement.create", "POST", "/demand/api/create", mutates=True)
    errors = binding.contract_errors()
    assert "mutating capability is not idempotent: requirement.create" in errors
    assert "mutating capability has no compensation: requirement.create" in errors


def test_invalid_binding_is_rejected_before_registration():
    with pytest.raises(ValueError, match="path must start"):
        build_real_pack("x", "1", [RealBinding("x", "GET", "bad")], request=lambda *_: {})
