import json

from core.approved_asset_execution import inject_approved_assets
from core.suite_compiler import compile_case
from core.suite_context import SuiteContext
from core.suite_dsl import case_content_hash


def test_approved_fixture_and_api_oracle_are_injected(tmp_path):
    suite = tmp_path / "suite"
    (suite / "approved_assets" / "fixtures").mkdir(parents=True)
    (suite / "approved_assets" / "oracles").mkdir(parents=True)
    (suite / "approved_assets" / "fixtures" / "f.yaml").write_text(
        "fixture_id: fixture:one\nstatus: approved\napproved_by: qa\nverified: true\n"
        "case_keys: [TC1]\nsteps:\n  - method: POST\n    url: /prepare\ncontent_hash: f-hash\n", encoding="utf-8"
    )
    (suite / "approved_assets" / "oracles" / "o.yaml").write_text(
        "oracle_id: oracle:one\ncase_id: suite/TC1\nstatus: approved\napproved_by: qa\n"
        "assertions:\n  - id: status\n    proof: api_response\n    subject: response.body.status\n    operator: equals\n    expected: READY\ncontent_hash: o-hash\n", encoding="utf-8"
    )
    case = {"case_id": "suite/TC1", "source": {"case_key": "TC1"},
            "execution": {"engine_assertions": {}, "assertion_bindings": {}}}
    result, metadata = inject_approved_assets(case, suite)
    assert result["execution"]["data_prep"][0]["url"] == "/prepare"
    assert result["execution"]["engine_assertions"]["response"]["body"]["status"] == "READY"
    assert result["execution"]["assertion_bindings"]["status"]["ref"] == "engine_assertions.response"
    assert metadata["fixture"]["content_hash"] == "f-hash"
    assert metadata["oracle"]["content_hash"] == "o-hash"


def test_unsupported_oracle_is_reported_not_silently_executed(tmp_path):
    oracle_dir = tmp_path / "suite" / "approved_assets" / "oracles"
    oracle_dir.mkdir(parents=True)
    (oracle_dir / "o.json").write_text(json.dumps({
        "oracle_id": "oracle:two", "case_id": "suite/TC2", "status": "approved", "approved_by": "qa",
        "assertions": [{"id": "event", "proof": "event", "subject": "event.name", "expected": "done"}],
    }), encoding="utf-8")
    result, metadata = inject_approved_assets({"case_id": "suite/TC2", "execution": {}}, tmp_path / "suite")
    assert result["execution"].get("engine_assertions", {}) == {}
    assert metadata["unsupported_oracles"][0]["id"] == "event"


def test_approved_assets_are_carried_into_compiled_exec_spec(tmp_path):
    workspace = tmp_path / "workspace"
    suite = workspace / "suites" / "demo"
    (suite / "approved_assets" / "oracles").mkdir(parents=True)
    (suite / "suite.yaml").write_text("suite_id: demo\n", encoding="utf-8")
    (suite / "approved_assets" / "oracles" / "o.yaml").write_text(
        "oracle_id: oracle:three\ncase_id: demo/TC3\nstatus: approved\napproved_by: qa\n"
        "assertions:\n  - id: status\n    proof: api_response\n    subject: response.status\n    operator: equals\n    expected: 200\ncontent_hash: o-hash\n", encoding="utf-8"
    )
    case = {
        "schema_version": 1, "case_id": "demo/TC3", "title": "API status", "suite_id": "demo",
        "status": "ready", "priority": "P1", "scenario_type": "query",
        "source": {"case_key": "TC3"}, "layers": {"required": ["api"]},
        "assertions": {},
        "actions": {"api": [{"request": {"method": "GET", "url": "/health"}}]},
        "cleanup": {"strategy": "marker", "targets": []},
        "execution": {"mode": "api", "request": {"method": "GET", "url": "/health"},
                       "cleanup": [{"table": "items", "column": "name"}],
                       "allowed_tables": ["items"]},
    }
    case["approval"] = {"status": "human_verified", "content_hash": case_content_hash(case)}
    spec = compile_case(case, {"suite_id": "demo"}, SuiteContext.create(suite, workspace))
    assert spec.assertions["response"]["status"] == 200
    assert spec.raw["approved_assets"]["oracle"]["content_hash"] == "o-hash"
