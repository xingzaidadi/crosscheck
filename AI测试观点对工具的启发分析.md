# AI 测试观点对工具的启发分析

## 核心判断

这段视频对我们的工具帮助很大。它实际上给出了一个非常重要的产品判断：

> **不要再笼统地问“AI 测试好不好用”，而要定义：在什么业务复杂度、什么自动化标准、什么资产沉淀目标下，工具是否达标。**

结合当前 `vendor-test-agent` 的能力，我认为可以提炼出以下结论。

## 一、对工具定位的启发

我们的工具不应该定位成“AI 自动点页面工具”，而应该定位成：

> **面向复杂业务链路的、可审计、可回归、可持续维护的 AI 测试工程平台。**

这和视频里提到的长期质量保障派高度一致。

当前仓库已经具备不少差异化基础：

- UI → API → DB 的跨层一致性校验
- 测试数据准备、标记、清理和哨兵保护
- 页面断言、接口断言、数据库断言
- 状态快照与 diff
- 用例 readiness / blocked 门禁
- 知识库审批和 hash 校验
- 资产 replay、人工审核、激活
- suite plan、证据链和执行报告
- 确定性回放优先，AI 自愈作为兜底

这些能力说明工具的方向已经不是简单 POC，而是在向生产级回归体系发展。

例如：

- `README.md:77` 已经体现“回放优先、AI 自愈兜底”
- `README.md:80` 已经体现页面、DB 和状态 diff 三重校验
- `README.md:81` 已经体现数据隔离和失败清理
- `ARCHITECTURE.md:21` 明确执行期不依赖 LLM，保证结果可比
- `core/asset_review.py` 已经有 replay asset 的审核和激活流程
- `core/readiness.py` 已经有用例可执行性门禁

因此，这段视频不是在否定我们当前路线，反而验证了路线是对的。

## 二、当前工具最需要补上的核心能力

### 1. 增加“业务复杂度分级”

视频第一个观点是：简单接口和复杂业务链路不是同一个问题。

当前工具虽然能够识别 UI、API、DB、写操作、查询、权限、工作流等维度，但还缺少一个面向用户的“业务复杂度评分”。

建议为每个 suite / case 增加类似字段：

```yaml
complexity:
  level: L3
  dimensions:
    dependency_count: 5
    state_dependency: high
    cross_system: true
    historical_rules: high
    async_dependency: medium
    data_setup_cost: high
```

可以定义四级：

| 等级 | 业务类型 | 典型场景 |
|---|---|---|
| L0 | 独立校验 | 简单接口、静态页面 |
| L1 | 单系统流程 | 查询、创建、编辑、删除 |
| L2 | 多步骤状态流转 | 审批、退款、订单状态变化 |
| L3 | 跨系统复杂链路 | 退款 + 库存 + 优惠 + 账户 + 消息 |
| L4 | 高风险核心链路 | 财务、支付、清算、权限、核心交易 |

这样工具可以在报告中明确告诉用户：

> 当前用例属于 L3 复杂业务，自动化阻塞点不是页面操作，而是测试数据、状态依赖和业务断言。

这比简单报告“执行失败”有价值很多。

### 2. 把“前置状态”从文本变成可执行资产

视频明确指出，真实业务最难的是：

- 指定账号
- 指定角色
- 指定订单状态
- 指定库存
- 指定优惠条件
- 指定历史数据
- 指定上下游系统状态

当前仓库已有：

- `core/state_recipe.py`
- `core/fixture_registry.py`
- `core/prep.py`
- `core/fixtures.py`
- UI fixture lifecycle
- data prep 和 cleanup 相关测试

但下一步需要把它们统一成一个明确的 **State Recipe / Business Fixture 模型**。

例如退款用例不应只是：

```yaml
case_id: refund_order
steps:
  - click: 退款
```

而应表达为：

```yaml
case_id: refund_order
preconditions:
  actor:
    role: customer_service
  order:
    status: paid
    has_coupon: true
    has_inventory: true
    payment_status: settled
  account:
    balance_status: normal
  inventory:
    available: true

state_recipe:
  - create_customer
  - create_product
  - reserve_inventory
  - create_paid_order
  - attach_coupon
  - settle_payment
```

执行失败时，报告要区分：

- 页面操作失败
- 数据准备失败
- 前置状态不存在
- 状态构造不完整
- 业务规则未配置
- 断言无法证明
- 环境依赖缺失

这会直接解决视频中“复杂业务觉得 AI 不好用”的主要痛点。

### 3. 建立“业务断言 / Oracle”能力

视频中很关键的一点是：

> 不是完成操作就算测试成功，而是要知道“什么叫退款正确”。

当前工具已有不错的基础：

- `core/oracle.py`
- API response assertion
- DB assertion
- UI value / visibility / field assertion
- cross-layer reconciliation
- evidence sufficiency

建议继续强化为 **业务 Oracle 层**，不要只提供字段相等断言。

例如退款正确可能同时要求：

```yaml
business_oracle:
  - order.status == refunded
  - refund.amount == payable_amount
  - inventory.released == true
  - coupon.restore_status == restored
  - payment.refund_status == success
  - audit_log.contains("refund")
  - no_duplicate_refund_record: true
```

报告应展示：

```text
业务结果：FAIL

已证明：
- UI 显示退款成功
- API 返回 HTTP 200
- 订单状态已变更为 refunded

未证明：
- 退款金额是否正确
- 库存是否释放
- 优惠券是否恢复
- 是否生成审计记录
- 是否存在重复退款
```

这比单纯输出“PASS / FAIL”更能体现工具的专业价值。

## 三、明确区分 POC、辅助执行和生产自动化

视频第二个维度非常适合直接转化成工具的交付等级。

建议把工具的运行模式明确拆成四级。

### Level 1：单次辅助验证

特点：

- 用户提供自然语言任务
- Agent 负责探索和操作
- 允许人工补充信息
- 允许人工修正步骤
- 输出截图和临时报告
- 不要求沉淀资产

适合：

- POC
- 新功能探索
- 临时验收
- 演示

### Level 2：受控重复执行

特点：

- 已有 profile、路由和用例
- 能自动准备基础数据
- 能重复回放
- 失败时保留证据
- 需要人工处理 blocked case

适合：

- 测试团队日常执行
- 版本验收
- 小批量回归

### Level 3：流水线自动回归

特点：

- 环境自动检查
- 登录态可复用
- 测试数据自动构造
- UI/API/DB 自动校验
- 失败自动分类
- 生成标准化报告
- CI 中无人值守运行
- 结果有稳定性指标

适合：

- 预发回归
- 发布门禁
- 核心模块回归

### Level 4：长期质量资产

特点：

- 自动生成或维护正式用例
- 用例有版本、来源和审批记录
- 绑定知识库 hash
- 页面变更后可以识别漂移
- 资产可 replay、review、activate
- 持续统计维护成本
- 低质量资产自动退休

适合：

- 核心业务
- 长期回归
- 大规模测试资产治理

当前仓库已经有 Level 2、Level 3 和 Level 4 的不少机制，但产品界面和报告中还没有明确告诉用户：

> 你当前完成的是哪一个等级，距离生产无人值守还差什么。

这是非常值得补的能力。

## 四、把“能跑一次”改成“可持续回归”指标

视频对我们的最大提醒是：

> 单次成功不是 AI 测试的最终价值，真正价值在于能否沉淀成长期资产。

因此建议在报告中增加以下指标。

### 1. 首次执行成功率

```text
first_run_success_rate
```

衡量 POC 和 Agent 执行能力。

### 2. 无人工干预成功率

```text
unattended_success_rate
```

衡量是否达到流水线标准。

### 3. 重复回放稳定性

```text
replay_stability
```

例如同一用例连续执行 20 次：

- 通过 19 次
- 失败 1 次
- 稳定性 95%

当前已有 `core/ui_agent/benchmark.py` 和相关 benchmark 测试，可以把它从 UI Agent 指标提升成统一资产指标。

### 4. 资产维护成本

```text
maintenance_cost:
  repair_count: 3
  manual_review_minutes: 20
  drift_rate: 0.08
  last_repaired_at: ...
```

### 5. 证明完整度

```text
proof_completeness:
  ui: true
  api: true
  db: true
  business_oracle: false
  evidence_complete: false
```

### 6. 业务风险覆盖率

```text
risk_coverage:
  happy_path: true
  negative_path: true
  permission: true
  idempotency: true
  concurrency: false
  async_consistency: false
```

这样就能避免用户只看一个“PASS”。

## 五、增加“AI 测试成熟度评估报告”

可以直接做成工具的核心输出之一。

报告回答五个问题。

### 1. 测的是什么复杂度？

```text
业务复杂度：L3 / 跨系统强状态链路
```

### 2. 当前自动化到哪一级？

```text
当前等级：Level 2 受控重复执行
目标等级：Level 3 CI 无人值守回归
```

### 3. 现在卡在哪里？

```text
阻塞项：
- 缺少退款前置状态构造器
- 缺少库存释放断言
- 缺少优惠券恢复断言
- 缺少异步消息消费证据
```

### 4. 已经沉淀了什么？

```text
已沉淀：
- 1 个 UI replay asset
- 3 个 API route
- 2 个 DB mapping
- 1 个 state recipe
- 5 个业务 oracle
```

### 5. 离生产还有多远？

```text
生产就绪度：62%

已满足：
- 可重复执行
- 数据隔离
- 失败证据
- UI/API/DB 断言

未满足：
- 无人值守成功率低于阈值
- 存在人工登录依赖
- 有 2 个未审批业务规则
- 异步链路无法证明
```

这可以把当前已有的 readiness、evidence、asset、maturity、suite plan 等能力统一起来。

## 六、把失败分类从“技术失败”升级为“落地障碍”

对于复杂业务，用户最想知道的不是“Agent failed”，而是为什么无法落地。

建议统一分类：

| 类别 | 含义 | 工具应给出的动作 |
|---|---|---|
| `environment_blocked` | 环境、账号、服务不可用 | 补环境或权限 |
| `data_blocked` | 无法构造业务前置数据 | 增加 fixture / recipe |
| `state_blocked` | 状态不满足 | 补状态转换步骤 |
| `oracle_blocked` | 不知道如何判定正确 | 配置业务断言 |
| `evidence_blocked` | 结果缺少可信证据 | 增加 API / DB / 日志证据 |
| `asset_blocked` | 无法沉淀稳定用例 | 修复 selector、绑定或路由 |
| `governance_blocked` | 知识未审批或已过期 | 重新评审知识和资产 |
| `runtime_failed` | 已具备条件但执行失败 | 进入缺陷分析 |

这会让工具从“执行器”升级为“落地诊断器”。

## 七、对当前工具的优先级建议

### P0：优先补齐

1. **业务复杂度评分**
2. **自动化交付等级**
3. **前置状态 / 测试数据依赖可视化**
4. **失败原因分类**
5. **生产就绪度报告**
6. **单次成功率与无人值守成功率区分**

这些能力主要是统一已有模块和报告，不一定需要大规模新增执行能力。

### P1：增强复杂业务落地

1. 统一 `state_recipe`、`fixture_registry`、`data_prep`
2. 增加业务 Oracle 模板
3. 增加跨系统异步链路证据
4. 增加状态机和状态转换图
5. 增加资产维护成本统计
6. 增加失败后自动复跑和回归关联

### P2：长期竞争力

1. 从执行结果反向沉淀业务知识
2. 根据历史失败自动推荐测试数据
3. 根据业务变更自动识别受影响用例
4. 自动生成回归范围
5. 自动识别“懂业务的人才知识”是否已沉淀
6. 形成业务域级质量知识图谱

## 八、对外和内部汇报时可以这样总结

可以把这段视频对工具的启发浓缩成一句话：

> 我们不把 AI 测试的成功标准定义为“能不能自动点完一次页面”，而是从业务复杂度、流水线无人值守能力和长期资产沉淀三个维度评估。对于复杂业务，工具的核心价值不只是执行操作，而是帮助准备前置状态、建立业务断言、保留跨层证据，并最终沉淀成可重复回归、可审计、可维护的测试资产。

再结合当前工具，可以进一步说：

> `vendor-test-agent` 当前已经具备跨 UI/API/DB 校验、数据隔离、状态 diff、知识审批、资产审核和 readiness 门禁等生产化基础。下一步重点是把这些能力统一成“复杂度分级 + 自动化成熟度 + 生产就绪度”的产品化评估体系，让用户清楚知道当前能做什么、不能做什么，以及距离无人值守回归还差哪些工程条件。

最后需要特别保留视频里的风险提醒：

> 工具应当沉淀业务知识，而不是掩盖业务知识缺失。AI 可以减少重复执行和脚本编写，但不能替代懂业务、懂系统、能判断风险的人。否则测试资产虽然越来越多，质量根基反而可能越来越弱。
