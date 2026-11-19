from __future__ import annotations

import json
from pathlib import Path

from core.framework import (CanonicalCase, build_capability_graph, fingerprint,
                            load_suite_assets, plan_onboarding, schemas, validate_document)


def test_framework_plan_is_deterministic(tmp_path: Path):
    profile = {"capabilities": [{"id": "generic-api", "layers": ["api"]}]}
    cases = [CanonicalCase("suite/a-1", "A", "A", "P1", ["query"], ["api"], "state ready")]
    graph = build_capability_graph(profile, tmp_path)
    first = plan_onboarding(cases, graph, profile)
    second = plan_onboarding(cases, graph, profile)
    assert fingerprint(first) == fingerprint(second)
    assert len(first["readiness"]) == 1
    assert len(first["fixture_requirements"]) == 1


def test_framework_plan_reports_missing_layer():
    profile = {"capabilities": [{"id": "generic-api", "layers": ["api"]}]}
    cases = [CanonicalCase("suite/a-1", "A", "A", "P1", ["query"], ["mq"])]
    report = plan_onboarding(cases, build_capability_graph(profile, Path(".")), profile)
    assert report["readiness"][0]["status"] == "BLOCKED"
    assert report["gap_report"]["gaps"][0]["type"] == "ENVIRONMENT_MISSING"


def test_canonical_schema_validation_is_real():
    schema = schemas()["canonical_case"]
    assert validate_document({"schema_version": 1, "case_id": "x", "title": "X",
                              "required_layers": ["api"]}, schema) == []
    assert validate_document({"schema_version": 1, "title": "X", "required_layers": "api"}, schema)


def test_reviewed_suite_assets_reduce_gaps(tmp_path: Path):
    suite = tmp_path / "suite"
    (suite / "generated_specs").mkdir(parents=True)
    (suite / "fixtures.yaml").write_text(
        "fixtures:\n  shared:\n    verified: true\n    case_keys: [C1]\n", encoding="utf-8")
    (suite / "generated_specs" / "C1.yaml").write_text(
        "case_id: C1\nmode: api\nverify_status: human_verified\nrequest:\n  url: /api/items\n"
        "engine_assertions:\n  response:\n    status: 200\n", encoding="utf-8")
    cases = [CanonicalCase("suite/C1-2", "A", "C1", "P1", ["query"], ["api"], "existing")]
    profile = {"base_url": "https://example.invalid"}
    assets = load_suite_assets(suite)
    report = plan_onboarding(cases, build_capability_graph(profile, tmp_path), profile, assets)
    types = {item["type"] for item in report["gap_report"]["gaps"]}
    assert "BINDING_REVIEW_REQUIRED" not in types
    assert "FIXTURE_MISSING" not in types
