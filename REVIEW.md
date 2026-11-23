# REVIEW.md — 框架改动的可靠性清单（diff 触发）

> **权威版本在 main 分支。** 本文件的判定版本由 `core/review_rules.read_base_review` 用
> `git show main:REVIEW.md` 从**基线分支**读取——改动分支/工作区里对本文件的修改**不参与判定**。
> 这是"改动不能改判它的检查"的落地（见《Claude验证方法论-文章精读.md》§三.6）。
>
> 用法：`crosscheck review-gate --base-ref main`。工具读当前改动命中的触发器，
> 只列命中的规则（通常 3–10 条），每条给出要检查什么、以及背后的事故，便于人判时不必从 diff 反推。

## 规则格式

每条规则一个 `## RULE:` 段，含三要素：
- `trigger`：能从改动路径/内容命中的触发器（文件路径子串，多个用逗号）。
- `check`：命中后要确认什么。
- `incident`：背后的事故/PR（说明为什么有这条）。

---

## RULE: pipeline-stop-path
- trigger: core/pipeline_runner.py
- check: 改了停止/熔断/checkpoint/resume 逻辑时，确认默认 resume=True 路径仍生效——失败 case 不被 continue 跳过而漏计熔断；已完成的非 PASS case 在跳过前仍 observe 一次。
- incident: 熔断 R1——默认 resume=True 下熔断曾形同虚设，测试用 resume=False 绕开。

## RULE: circuit-breaker-count
- trigger: core/circuit_breaker.py
- check: 改了计数/清零/阈值/持久化时，确认 (case_id, failure_class) 粒度不变、成功删 key 而非置 0、终态类（SPEC/SAFETY/CLEANUP）永不触发、to_dict/from_dict 往返无损。
- incident: 熔断 R2（reset 置 0 致状态膨胀）、M3（cleanup 须优先于熔断）。

## RULE: quality-gate-policy
- trigger: core/quality_gate.py, scripts/quality_gate.py
- check: 改了门禁判定/阈值/三档时，确认默认 mode=enforce 保持旧行为、observe 不阻断（passed=True）、放宽门槛只改配置不改报告含义、验证戳为附加字段不改判定。
- incident: 门禁放宽若改了报告措辞会伪造成熟度（见 IMPLEMENTATION_STATUS "不得通过改措辞提升等级"）。

## RULE: review-rules-immutability
- trigger: core/review_rules.py, REVIEW.md
- check: 改了规则读取逻辑时，确认判定版本仍从 base 分支读（git show base:REVIEW.md），绝不回退到读工作区文件——否则改动可篡改判它的规则。
- incident: 不可篡改是验证层信任根基（文章 §三.6）。

## RULE: asset-health-threshold
- trigger: core/asset_health.py, core/asset_recertification.py
- check: 改了健康阈值/连续失败计数/隔离逻辑时，确认 degraded/unhealthy 判定与门禁一致，unhealthy 资产不被加载执行。
- incident: 资产健康是门禁的输入，阈值漂移会放行不健康资产。

## RULE: approval-hash-integrity
- trigger: core/remediation_review.py, core/approved_assets.py, core/suite_compiler.py
- check: 改了审批/内容哈希/canonical 编译时，确认资产不经命名人审 + 哈希绑定不得晋级，哈希排除易变字段后可复现。
- incident: 自动生成草稿绕过人审会让模型猜测进入正式 PASS。

## RULE: cleanup-safety-net
- trigger: core/cleaner.py, core/executor.py
- check: 改了清理/写入/allowed_tables 时，确认 cleanup 是显式白名单、变更表 ⊆ allowed_tables、表名列名校验为 SQL 标识符、失败也清且有兜底。
- incident: 数据隔离红线（README 安全边界）。
