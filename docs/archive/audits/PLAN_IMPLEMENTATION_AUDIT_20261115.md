# docs 计划实现覆盖审计（2026-11-15）

## 结论

`docs` 中计划描述的内容**没有全部实现**。当前已经完成通用执行底座、Case v2 最小契约、本地业务链路、UI-first 运行模型、基础资产治理、视觉比较内核和严格验收门禁；但真实业务武器包、142 条 UI 绑定、Stage 2/3 独立 API/DB 产品闭环、完整视觉产品、第二真实系统 external_pass 等仍未完成。

## 本轮完成的 UI-first 优化

- UI 阶段只要求 UI binding；API/DB 作为 optional/deferred，不再阻塞 UI 结论。
- 新增 `UI_PASS/UI_FAIL` 阶段结论，API/DB 未覆盖明确显示 `NOT_COVERED`。
- 新增 `upload`、`download`、`assert_visible` UI 动作。
- 上传证据记录文件路径、大小和 SHA-256。
- 下载可校验文件名、最小大小和 SHA-256。
- 新增业务目标证据充分性模型：页面上传下载和业务库中的外部结果可以证明业务功能；只有明确测试传输链路时才要求 provider/producer 证据。
- 新增 UI-first readiness 报告和 evidence audit。
- 142 条当前 UI 矩阵：12 条 UI_EXECUTABLE、121 条 UI_BINDING_REQUIRED、9 条 UI_BLOCKED。

## 文档逐项状态

| 文档 | 计划块 | 状态 | 说明 |
|---|---|---|---|
| AI_EXECUTABLE_CASES_PLAN | Phase 0 v2 契约 | 基本完成 | v2 schema、迁移、oracle、wait 已有；canonical 唯一原生 v2 链仍未完全替换 legacy projection |
| AI_EXECUTABLE_CASES_PLAN | Phase 1 审计器 | 完成基础版 | 质量、歧义、重复、READY 缺口已实现 |
| AI_EXECUTABLE_CASES_PLAN | Phase 2 知识闭环 | 部分完成 | knowledge、候选和审批存在；需求/规则自动生成及来源完整性尚不全面 |
| AI_EXECUTABLE_CASES_PLAN | Phase 3 执行绑定 | 部分完成 | binding candidate、录制、API catalog、DB schema 已有；142 条仅 12 条 UI executable |
| AI_EXECUTABLE_CASES_PLAN | Phase 4 武器依赖 | 部分完成 | DAG、变量、lease、create-if-missing 原语已有；真实完整业务 planner 未完成 |
| AI_EXECUTABLE_CASES_PLAN | Phase 5 反馈优化 | 部分完成 | 失败分类、漂移率、报告存在；自动基于历史结果优化模板尚未闭环 |
| BUSINESS_TEST_ARSENAL_PLAN | Phase 0 契约样例 | 部分完成 | Capability/Object/Plan dataclass 和校验已有；计划所列独立 JSON schema 文件未创建 |
| BUSINESS_TEST_ARSENAL_PLAN | Phase 1 最小闭环 | local_e2e 完成 | requirement/strategy 本地 mock、登记、幂等、清理和血缘已实现；真实业务能力未完整 |
| BUSINESS_TEST_ARSENAL_PLAN | Phase 2 受控 DB 准备 | 部分完成 | DB 安全和方言门禁已有；完整白名单字段写入、快照回滚产品链未闭环 |
| BUSINESS_TEST_ARSENAL_PLAN | Phase 3 链路扩展 | local_e2e 完成 | G4/G5 mock 可验收；真实招采、合同、订单未完成 |
| BUSINESS_TEST_ARSENAL_PLAN | Phase 4 Skill 入口 | 部分完成 | Skill/CLI/确定性校验已有；自然语言到已批准能力的完整 planner 未完成 |
| CASE_ARSENAL_MASTER_PLAN | Stage 0/WP01-06 | 基本完成 | 契约、审计、注册表、DAG、运行登记、失败分类已有 |
| CASE_ARSENAL_MASTER_PLAN | Stage 1/WP07 | local_e2e 完成 | 本地需求能力包完成；真实需求能力包部分可用，不是完整正式包 |
| CASE_ARSENAL_MASTER_PLAN | Stage 2-5/WP08 | local_e2e 完成 | 本地策略到订单链完成；真实业务链未完成 |
| CASE_ARSENAL_MASTER_PLAN | WP09/Gate | 部分完成 | 报告、残留、能力健康和门禁基础存在；责任人签署和发布治理不完整 |
| CASE_ARSENAL_MASTER_PLAN | UI 资产流水线 | 部分完成 | candidate→replay_verified→human_verified→approved→healthy 已实现；自动生成三类候选与大规模 replay 未完成 |
| CASE_ARSENAL_MASTER_PLAN | 分层执行 | 基本机制完成 | 独立 subplan、retry、checkpoint、CROSS_* 已实现；尚未全面接入所有正式执行入口 |
| UNIFIED_DOCUMENTATION... | Stage 0 | 基本完成 | 安全、契约、分层、登记、gate 基础完成 |
| UNIFIED_DOCUMENTATION... | Stage 1 UI | 进行中 | UI-first 模型与文件动作已完成；142 条仅 12 条已有可执行 UI 绑定 |
| UNIFIED_DOCUMENTATION... | Stage 2 API | 未完成产品闭环 | 有 API adapter/catalog/断言，但未成为独立全面阶段 |
| UNIFIED_DOCUMENTATION... | Stage 3 DB | 未完成产品闭环 | 有 DB 对账/schema map，但独立恢复、checkpoint 和全量契约未完成 |
| UNIFIED_DOCUMENTATION... | Stage 4/5 | local_e2e | mock G4/G5 完成，真实业务未完成 |
| UNIFIED_DOCUMENTATION... | Stage 6 | 部分完成 | 像素、mask、结构比较和 baseline 存储已有；固定浏览器采集和完整审批 workflow 未完成 |
| UNIFIED_DOCUMENTATION... | Stage 7 | 未完成 | 合同测试和 external_ready 有，第二真实业务 external_pass 没有 |

## 明确未实现或未完全实现

1. 142 条用例的完整 UI action binding 和稳定 replay。
2. 真实 `requirement.create/find/submit/approve/verify/cancel` 全能力包及统一补偿。
3. 真实策略、招采、合同和订单累计链路。
4. Case v2 作为唯一 canonical 存储、编译和原生执行协议。
5. 所有正式执行入口全面使用独立 UI/API/DB subplan。
6. Stage 2 独立 API 测试产品：契约、权限、幂等、并发、重试和 UI 关联全覆盖。
7. Stage 3 独立 DB 测试产品：租户、组织、主子表、金额、审计、最终一致性和恢复全覆盖。
8. 自动从 UI 捕获生成 case/capability/knowledge 三类候选并完成批量 replay 审批。
9. 固定 Chromium、字体、viewport、locale/timezone 的自动视觉 baseline 采集。
10. 第二个无关真实系统的 `external_pass`。
11. 功能级冻结测试集合、结果自动回填 manifest 和连续 soak 的完整 100% gate。
12. 计划文档中提到的独立 `capability.schema.json`、`object.schema.json`、`plan.schema.json` 和 `core/plan_compiler.py` 文件形态尚不存在；能力由现有 Python 模型分散承载。

## 下一步

当前不应立即扩展 API/DB 阶段。下一步应完成 Stage 1：

1. 为 121 条 `UI_BINDING_REQUIRED` 用例按模块录制和生成 UI candidate。
2. 先处理 P0，再处理 P1；每个 candidate 必须 replay_verified 后才能批准。
3. 优先补齐上传、下载、导入、导出、查询、详情、按钮和字段联动等页面可直接判断场景。
4. 执行 UI pilot，稳定后批量运行全部 UI_EXECUTABLE。
5. 将 API 请求、业务 ID 和 DB 关联仅作为采集素材，不阻断 UI verdict。
6. Stage 1 达到承诺范围后，再进入 Stage 2 API 独立验证。
