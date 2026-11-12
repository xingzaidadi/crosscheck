# 通用工具验收结果

- 通过: 13/13

|ID|验收项|结果|证据|
|---|---|---|---|
|P0-01|空数据和基数不足不能 PASS|PASS|`tests/test_empty_evidence_gate.py`|
|P0-02|套件/审批/内容哈希漂移拒绝|PASS|`tests/test_suite_compiler.py`|
|P0-03|旧编号与陈旧路由污染拒绝|PASS|`tests/test_route_fidelity.py`|
|P0-04|清理失败和登记册安全门禁|PASS|`tests/test_cleaner_child.py`|
|P0-05|非生产授权门禁|PASS|`tests/test_run_suite_cli.py`|
|P1-01|Canonical 编译为不可变执行计划|PASS|`tests/test_suite_compiler.py`|
|P1-02|Pilot/批量/熔断/恢复状态机|PASS|`tests/test_pipeline_runner.py`|
|P1-03|连接器配方与变更审批失效|PASS|`tests/test_suite_bindings.py`|
|P1-04|case-gen YAML 直接导入|PASS|`tests/test_casegen_import.py`|
|P1-05|断言级结果和跨运行报告|PASS|`tests/test_report_index.py`|
|P2-01|两个无关业务不改 core 编译|PASS|`tests/test_cross_domain_canonical.py`|
|P2-02|发布白名单和秘密扫描|PASS|`tests/test_release_policy.py`|
|P2-03|Skill 流水线结构有效|PASS|`.agents/skills/crosscheck/SKILL.md`|