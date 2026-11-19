# Crosscheck 文档统一总方案与实施状态

> 本文保留为跨规划的综合设计基线。日常文档入口与归档清单以 `docs/README.md` 为准；历史计划和审计已迁入 `docs/archive/`。

## 1. 一句话结论

当前 Crosscheck 已经从测试脚本发展为一个具备 UI/API/DB 执行、canonical 用例、审批哈希、知识闭环、清理、安全扫描、运行事件和武器库底层原语的工程原型；但距离我们最终要的“AI 可执行用例 + 业务武器库 + 依赖编排 + 分层执行 + 真实业务链路 + 视觉对比”仍有关键产品能力未完成。

当前准确定位：

```text
通用测试框架底座：较完整
业务 Agent 闭环：未完成
真实外部业务验收：未完成
```

离线测试通过不等于业务系统通过；文档中的设计评分也不等于实现成熟度。

## 2. docs 文档地图

| 文档 | 定位 | 结论 |
|---|---|---|
| `archive/plans/OPTIMIZATION_ROADMAP.md` | 根因审计和优先级路线 | 历史 P0/P1/P2 纠偏基线 |
| `GENERAL_TOOL_ACCEPTANCE.md` | 通用平台最终验收标准 | 结果真实性、通用性和负向实验的硬门禁 |
| `GENERAL_TOOL_ACCEPTANCE_RESULTS.*` | 当前验收证据 | 25/25，但主要是 contract/local_e2e，不是外部业务 PASS |
| `IMPLEMENTATION_STATUS.md` | 实现侧真实状态 | 当前唯一的实现完成度对照表 |
| `archive/plans/CASE_ARSENAL_MASTER_PLAN.md` | 用例×武器库主设计 | 历史产品架构和阶段门禁基线 |
| `archive/plans/AI_EXECUTABLE_CASES_PLAN.md` | AI 可执行用例工程 | Case v2、oracle、来源、AI 草拟和质量评分 |
| `archive/plans/BUSINESS_TEST_ARSENAL_PLAN.md` | 业务武器库设计 | 能力契约、对象、计划、DB 安全、补偿和业务链路 |
| `ONBOARDING.md` | 新系统接入操作 | workspace、profile、路由、运行和安全红线 |
| `PRODUCT_USAGE.md` | 产品使用入口 | CLI、知识、dashboard、map、readiness 和 demo |
| `COMPATIBILITY.md` | 支持边界 | Windows/Chromium/REST/JSON/MySQL 正式范围 |
| `RELEASE_CHECKLIST.md` | 发布门禁 | 测试、验收、分发、安全和外部证据 |
| `TROUBLESHOOTING.md` | 运维处理 | 安装、登录、UI、API、DB、清理和知识问题 |
| `external-acceptance.example.yaml` | 外部验收输入模板 | 真实业务系统证据清单模板 |

### 2.1 文档之间的优先级

发生冲突时，按以下顺序解释：

1. `GENERAL_TOOL_ACCEPTANCE.md` 的结果真实性和安全红线；
2. `IMPLEMENTATION_STATUS.md` 的实际完成状态；
3. `archive/plans/OPTIMIZATION_ROADMAP.md` 的已识别 P0/P1/P2 根因；
4. `archive/plans/CASE_ARSENAL_MASTER_PLAN.md` 的目标架构和阶段门禁；
5. 用例、武器库和产品使用文档的具体设计；
6. onboarding、发布和故障手册的操作细节。

规划文档只能提出目标，不能把“设计存在”写成“能力实现”。

## 3. 已经完成的能力

### 3.1 通用执行底座

- UI、API、DB 适配器和基础执行器；
- Playwright Chromium 页面执行；
- API 请求、响应和登录态处理；
- MySQL 正式支持、SQLite 本地演示；
- 页面录制、动作捕获、截图和 trace；
- 数据库查询、快照、映射和清理；
- canonical suite 加载、评分、编译和审批 hash；
- pilot、批量、checkpoint、恢复和报告基础能力。

### 3.2 结果真实性和安全基础

- 空数据/不足证据不能 PASS；
- 套件、连接器、内容和知识 hash 漂移拒绝；
- 断言必须绑定实际 proof；
- 写入需要 cleanup 和 `allowed_tables`；
- 失败分类和运行事件；
- SQLite 运行登记册、对象、租约、步骤和审计事件；
- pip-audit、bandit、发布白名单和秘密扫描；
- 本地 UI/API/SQLite/清理 demo。

### 3.3 当前验证结果

当前仓库回归基线：

```text
python -m pytest -q       51 passed
专项武器/运行时测试       9 passed
通用验收矩阵               25/25（以文档记录为准）
```

这些结果的 verification level 主要是 `contract` 和 `local_e2e`，不等于 `external_pass`。

## 4. 只实现了底座、尚未完成的能力

### 4.1 真实业务武器包

目前有 business-neutral 的 `Capability`、`ObjectRecord`、`Lease`、`ArsenalPlan` 和依赖规划原语，但没有真实业务能力包：

```text
requirement.create/find/submit/approve/verify/cancel
strategy.publish/verify/cancel
sourcing.publish
contract.sign
order.create
```

### 4.2 完整依赖规划

当前可加载能力、筛选健康状态并生成基础计划，但还没有完整执行：查询现有对象、原子 claim、状态转换搜索、字段维护策略、递归依赖、变量绑定、能力冲突、角色切换、成本选择和计划审批。

### 4.3 Case v2

当前 canonical 仍以 v1 的 `layers/actions/assertions/execution` 为主，尚未完整落地：

```text
traceability
intent.under_test
preconditions
action.capability
oracles
wait
open_questions
```

### 4.4 UI 资产化

已有录制和捕获，但没有端到端完成：

```text
捕获 → 语义动作 → case candidate
     → capability candidate
     → knowledge candidate
     → 脱敏参数化
     → 独立回放验证
     → human_verified
     → approved + healthy
```

### 4.5 UI/API/DB 分层模型

当前有层和 proof binding，但尚未支持完整的：

- `required/optional/deferred`；
- layer subplans；
- 每层独立状态和 checkpoint；
- `INCONCLUSIVE`；
- 层内断言与层间契约分离；
- 单层 ENV_ERROR 不污染其他层结果。

### 4.6 视觉/原型对比

尚未开始实现组件基线、动态 mask、结构/语义对比、像素阈值、视觉审批和视觉回归门禁。

### 4.7 真实外部验收和 100% 功能门禁

当前没有真实业务系统的 external acceptance evidence，也没有把“每个小功能承诺范围内 100%”做成功能级自动 gate，包括冻结验收 manifest、连续 soak、故障注入、残留为零和 DONE 阻止器。

## 5. 统一目标架构

```text
PRD/规则/Excel/Markdown/OpenAPI/DB schema/录制
  → 事实抽取和来源追踪
  → Case v2（测试意图）
  → 用例审计和缺口问题
  → 武器库依赖规划
  → 不可变执行计划
  → UI/API/DB 分层执行
  → 独立 oracle + 层间契约
  → 证据、血缘、补偿和结果归因
  → 知识、用例和能力健康度回流
```

### 5.1 人、AI、工具边界

| 角色 | 责任 |
|---|---|
| 业务/产品 | 业务真相、状态、角色、规则、成功失败和不可逆边界 |
| 测试 | 覆盖、风险、负向/边界/权限/幂等和证据审查 |
| AI | 事实抽取、测试点、草稿、缺口、能力和 proof 推荐 |
| 编译器/执行器 | schema、hash、计划、执行、断言、清理和报告 |

AI 不得无来源决定业务规则，不得在正式执行时临场改动作或断言。

## 6. 统一用例模型

一条用例只验证一个主要业务结论：

```yaml
schema_version: 2
case_id: strategy-publish-001
traceability:
  requirements: [PRD-123]
  rules: [RULE-STRATEGY-007]
intent:
  under_test: strategy.publish
preconditions:
  - object: requirement
    state: APPROVED
    strategy: create
    conditions:
      amount: {gte: 100000}
action:
  capability: strategy.publish
  inputs:
    requirement_id: "{{ requirement.id }}"
oracles:
  - id: A-REL-001
    subject: strategy.requirement_id
    operator: equals
    expected: "{{ requirement.id }}"
    proof_candidates: [api, db]
layers:
  required: [ui]
  optional: []
  deferred: [api, db]
```

业务断言和 UI/API/DB proof 分离；预期必须可判定，不能只写“成功、正常、正确”。

## 7. 统一武器库模型

武器能力分类：

```text
find       查询并 claim
create     创建对象
transition 推进状态
maintain   受控补齐字段/关系
verify     独立验证
compensate 取消/失效/冲正/删除
```

每个能力必须声明：输入、输出、requires、provides、actor、environment、effects、reads、writes、invalidates、evidence、idempotency、compensation、owner、version、health 和 hash。

DB maintain 只用于准备上游，不得替代当前 `under_test` 的真实 UI/API 动作。写风险按 `effects.mutates` 判断，不按 UI/API/DB 通道判断。

## 8. 统一执行原则

### 8.1 UI/API/DB：层内独立、层间契约、最终交叉

```text
UI  → UI_PASS/FAIL/ENV_ERROR/DRIFT
API → API_PASS/FAIL/ENV_ERROR/DRIFT
DB  → DB_PASS/FAIL/ENV_ERROR/DRIFT
          ↓
UI↔API、API↔DB、必要时 UI↔DB
          ↓
CROSS_PASS/CROSS_FAIL/CROSS_INCONCLUSIVE
```

一层环境错误不能污染另一层结果；三源交叉仍是最终验收能力。

### 8.2 100% 完成原则

功能开始前冻结验收集合。承诺范围内：正向、负向、边界、权限、幂等、异常、恢复、安全、证据、清理和回归都 100% 通过才能 `DONE`。`SKIP/XFAIL/ENV_ERROR/UNKNOWN/CLEANUP_FAILED` 不计成功。

### 8.3 UI 成功操作必须沉淀

```text
原始捕获
→ 语义动作
→ case/capability/knowledge candidate
→ 脱敏参数化
→ replay + 独立验证
→ 人工审批
→ approved + healthy
```

不为每个动作创建顶层 Skill；保留少量 `case-engineer`、`arsenal-planner`、`business-flow-builder`、`capability-maintainer`，具体业务动作使用结构化能力。

## 9. 统一分期路线

### Stage 0：契约和纠偏底座

- 修复历史 P0：唯一编译路径、状态/哈希/套件隔离、专用 oracle、空证据门禁、写入清理门禁；
- Case v2、Capability、Object、Plan schema；
- `required/optional/deferred` 和分层结果；
- 事务登记册、租约、步骤恢复、失败分类、100% gate。

### Stage 1：UI 需求场景

- UI 行为和 UI 业务断言；
- 采集 API 请求、业务 ID 和 DB 关联素材，但 API/DB 暂为 deferred；
- `requirement.create/find/submit/approve/verify/cancel`；
- UI 资产化 G-A；
- 节点测试和需求累计链路 100%。

### Stage 2：API 独立验证

- API 契约、错误、权限、幂等、并发和重试；
- UI↔API 字段、ID、状态和请求关联；
- 将 API 提升为 required；
- 独立 API 失败不覆盖 UI 结果。

### Stage 3：DB 独立验证

- 主子表、关联、状态、金额、组织、租户和审计；
- API↔DB 和必要的 UI↔DB 契约；
- 异步最终一致性和行级不变式；
- 将 DB 提升为 required。

### Stage 4：策略和招采

- `strategy.publish/verify/compensate`；
- 1+2、1+2+3 累计链路；
- 招采跨角色、异步事件和策略关联。

### Stage 5：合同和订单

- 不可逆电子签和外部同步；
- 金额、数量、预算、库存和订单幂等；
- 人工接管和补偿。

### Stage 6：原型/视觉对比

- 结构/语义对比；
- 组件级基线；
- 动态区域 mask；
- 像素阈值和视觉审批；
- 浏览器、字体、viewport 基线。

### Stage 7：最终通用性和外部验收

- 两个无关业务不修改 core；
- case-gen、Excel、YAML 统一进入 canonical；
- 全链路、清理、恢复、负向和安全实验；
- 外部证据达到 `external_pass`。

## 10. 统一检查点

| Gate | 主要输出 | 不能通过的条件 |
|---|---|---|
| G0 事实 | 状态机、角色、环境、规则、owner | 业务真相未知或环境未知 |
| G1 契约 | Case/Capability/Object/Plan schema 和迁移 | 未知字段、变量、operator、重复 ID |
| G2 安全运行时 | 环境指纹、租约、恢复、熔断、100% manifest | 生产/未知环境、无补偿、unknown 盲重试 |
| G-A 资产 | UI 捕获、候选用例/能力/知识、回放、审批 | 未脱敏、未独立验证、非 approved+healthy |
| G-L 分层 | required/optional/deferred、层内结果和契约 | 一层错误污染其他层或未执行显示 PASS |
| G3 需求 | 需求能力包和 UI 节点 | 5 次 soak、故障恢复、清理、独立证据未 100% |
| G4 1+2 | 需求→策略累计链路 | 输出变量、血缘、补偿和失败归因不完整 |
| G5 交付 | 文档、报告、外部证据、回滚联系人 | 只有 contract/local_e2e 或存在残留 |

## 11. 指标和状态口径

必须分开报告：

- Schema 合规率；
- 编译成功率；
- 业务充分率；
- 前提就绪率；
- 实际断言覆盖率；
- 自动推进率；
- 清理成功率；
- 能力健康度；
- external acceptance level。

统一状态：

```text
CASE_PASS
CASE_FAIL
PARTIAL
BLOCKED
INVALID_SPEC
ENV_ERROR
NOT_RUN
INCONCLUSIVE
```

任何情况下不能把 `PARTIAL`、`BLOCKED`、`ENV_ERROR`、`NOT_RUN`、`INCONCLUSIVE` 表述为通过。

## 12. 当前实现与目标差距表

| 能力 | 当前状态 | 下一步 |
|---|---|---|
| 通用 UI/API/DB 执行 | 已实现底座 | 分层子计划和独立结果 |
| canonical compiler | 已有并通过离线契约 | 对照 Case v2 和唯一编译路径继续加硬门禁 |
| 失败分类/运行事件 | 已实现底座 | 接入所有 layer/step/asset 结果 |
| 运行登记册/租约/checkpoint | 已实现原语 | 与真实能力和对象生命周期接通 |
| 武器库 | 有业务中立原语 | 实现需求能力包和递归 planner |
| Case v2 | 未完成 | schema、迁移器、审计器和 oracle |
| UI 资产化 | 未完成 | candidate→approved+healthy 流程 |
| 分层 required/optional/deferred | 未完成 | layer plans、INCONCLUSIVE 和报告 |
| 真实需求/策略链路 | 未完成 | G3/G4 外部验收 |
| 视觉/原型对比 | 未开始 | Stage 6 |
| 功能级 100% gate | 未完成 | acceptance manifest、soak、fault injection |
| 外部双系统验收 | 未完成 | external evidence manifest 和真实运行 |

## 13. 立即执行清单

### 第一个迭代只做这些

1. 固定 Case v2 最小 schema：`intent/preconditions/action/oracles/layers`。
2. 增加 v1→v2 迁移和静态审计，不破坏现有用例。
3. 实现 `required/optional/deferred` 与 `INCONCLUSIVE`。
4. 增加功能验收 manifest 和 100% DONE gate。
5. 用离线 mock 完成 `requirement.create` 能力包。
6. 增加 UI 捕获到 candidate case/capability 的最小流程。
7. 写 G0、G1、G2、G-A、G-L 的自动化检查。

### 第二个迭代

1. 接入真实需求创建 UI。
2. 连续 5 次稳定运行。
3. 完成超时、重复提交、清理失败和恢复测试。
4. 完成 `requirement.find/submit/approve/verify/cancel`。
5. 通过 G3 后再开始 API 关联。

### 第三个迭代

1. API 独立能力和 UI↔API 契约。
2. 需求→策略 1+2 链路。
3. 按 G4 做累计回归。
4. 通过后再接 DB。

## 14. 最终结论

`docs/` 下的内容并不是互相独立的多个方向，而是四类信息：

```text
历史问题审计：OPTIMIZATION_ROADMAP
目标设计：CASE_ARSENAL_MASTER_PLAN / AI_EXECUTABLE_CASES_PLAN / BUSINESS_TEST_ARSENAL_PLAN
通用验收：GENERAL_TOOL_ACCEPTANCE / RESULTS
当前事实：IMPLEMENTATION_STATUS
```

合并后，项目真实状态不是“已经做完”，也不是“还没开始”，而是：

> 通用测试和安全底座已具备；下一阶段必须把 Case v2、分层执行和第一个真实业务武器 `requirement.create` 做成 100% 可验收闭环。

推荐的第一条完整交付链：

```text
Case v2
→ requirement.create
→ UI 层独立 PASS
→ UI 资产化
→ G-A/G-L/G3 通过
→ API 独立关联
→ 需求→策略累计链路
→ G4 通过
```

只有这条链路真实通过，Crosscheck 才从“通用测试框架”进入“业务测试 Agent”阶段。
