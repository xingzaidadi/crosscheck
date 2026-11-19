# General Tool Acceptance

- Passed: 28/28

|ID|Check|Result|Level|Evidence|
|---|---|---|---|---|
|P0-01|Empty evidence cannot pass|PASS|contract|`tests/test_empty_evidence_gate.py`|
|P0-02|Approval and content hash drift rejection|PASS|contract|`tests/test_suite_compiler.py`|
|P0-03|Stale route fidelity rejection|PASS|contract|`tests/test_route_fidelity.py`|
|P0-04|Cleanup and registry safety gate|PASS|contract|`tests/test_cleaner_child.py`|
|P0-05|Non-production authorization gate|PASS|contract|`tests/test_run_suite_cli.py`|
|P1-01|Canonical immutable execution plan|PASS|contract|`tests/test_suite_compiler.py`|
|P1-02|Pilot batch resume state machine|PASS|contract|`tests/test_pipeline_runner.py`|
|P1-03|Connector binding approval|PASS|contract|`tests/test_suite_bindings.py`|
|P1-04|Case-gen YAML import|PASS|contract|`tests/test_casegen_import.py`|
|P1-05|Assertion and run report index|PASS|contract|`tests/test_report_index.py`|
|P2-01|Cross-domain canonical compilation|PASS|contract|`tests/test_cross_domain_canonical.py`|
|P2-02|Release allowlist and secret scan|PASS|contract|`tests/test_release_policy.py`|
|P2-03|Skill pipeline structure|PASS|contract|`.agents/skills/crosscheck/SKILL.md`|
|P2-04|Installed product CLI and templates|PASS|contract|`tests/test_product_cli.py`|
|P2-05|Knowledge and system-map extensions|PASS|contract|`tests/test_product_extensions.py`|
|P2-06|Two isolated system plans|PASS|local_e2e|`tests/test_two_system_e2e.py`|
|P2-07|Public Playwright adapter|PASS|contract|`tests/test_playwright_adapter.py`|
|P2-08|Local UI API DB cleanup demo|PASS|local_e2e|`tests/test_local_demo.py`|
|P2-09|External two-system evidence contract|PASS|external_ready|`tests/test_external_acceptance.py`|
|P2-10|Package resource completeness|PASS|contract|`tests/test_package_resources.py`|
|P2-11|API session refresh and redaction|PASS|contract|`tests/test_api_refresh_evidence.py`|
|P2-12|Protocol and database plugin contracts|PASS|contract|`tests/test_plugins.py`|
|P2-13|Database dialect guard|PASS|contract|`tests/test_db_dialect_guard.py`|
|P2-14|Security check entrypoint|PASS|contract|`tests/test_security_check.py`|
|P2-15|Pytest entry and SQLite fixtures|PASS|contract|`tests/test_report_index.py`|
|P2-16|Binding lifecycle drift and external adapters|PASS|contract|`tests/test_gap_closures.py`|
|P2-17|UI-first readiness and file evidence|PASS|contract|`tests/test_ui_first.py`|
|P2-18|Evidence sufficiency by test objective|PASS|contract|`tests/test_evidence_sufficiency.py`|