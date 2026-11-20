# 用例驱动的自主 UI 测试

## 产品原则

用例是测试范围和业务意图的主来源；Agent 负责把用例翻译成可执行计划，
探索页面、补齐定位和记录证据。代码、技术方案、数据库和接口资料是辅助
证据，不替代用例，也不要求用户把它们改写成自动化代码。

## 最小使用方式

```powershell
crosscheck test `
  --cases .\cases\orders.xlsx `
  --url https://test.example.com `
  --workspace .\workspace
```

支持 `xlsx`、`csv`、`json`、`yaml`/`yml`。至少需要“用例名称”；推荐提供：

- `用例等级`
- `所属模块`
- `前置条件`
- `步骤描述`
- `预期结果`
- `标签`

## 代码、方案、数据库怎么用

通过重复 `--source` 提供文件或目录：

```powershell
crosscheck test --cases .\cases\orders.yaml `
  --url https://test.example.com `
  --source .\backend `
  --source .\docs\order-design.md `
  --source .\db\schema.sql `
  --workspace .\workspace
```

工具会只读索引这些材料，生成 `source_manifest.json`，保存：

- 文件路径和 SHA-256
- 文件类型和大小
- API、数据库、权限、状态机、校验、异步等信号
- 可追溯短摘录

当前版本不会执行源码、不会执行来源不明脚本、不会自动修改数据库。
后续 UI/API/DB 规划可引用这些证据。

## 计划模式

先看 Agent 将如何解释用例，不执行浏览器：

```powershell
crosscheck test --cases .\cases\orders.xlsx `
  --url https://test.example.com `
  --workspace .\workspace `
  --source .\backend `
  --plan-only
```

输出目录包含：

- `case_plan.json`：每条用例的动作、断言、未解析预期和来源引用
- `source_manifest.json`：代码、方案、数据库等材料清单
- `coverage.json`：当前用例覆盖和未执行清单

## 执行产出

正式执行后额外生成：

- `summary.json`：总结果和每条用例结果
- `coverage.json`：用例级状态、断言数、证据路径、来源引用
- 每条用例的截图、HTML、trace 和恢复记录
- 通过的低风险 UI 路径可进入 provisional 回归资产

结果严格区分：`PASSED`、`FAILED`、`BLOCKED`、`AUTH_REQUIRED`、`ENV_ERROR`、
`NEEDS_INPUT` 和 `PLANNED`。未执行的用例进入 `not_covered`，不计为通过。

## 用例建议

用户可以只提供业务用例，不需要另外解释模块、角色、流程和风险。若用例
包含这些信息，Agent 会直接使用；若用例没有写明，Agent 只能把可从页面
确认的行为执行出来，并在覆盖报告中标记缺少的角色、数据或业务断言。

推荐每条用例表达为：

```yaml
cases:
  - name: TC-ORDER-001 查询处理中订单
    level: P0
    module: 订单管理/查询
    preconditions: 使用客服角色；存在 AUTOTEST_ 前缀订单
    steps: 输入客户名称华东并查询；打开第一条订单
    expected: 结果显示华东；详情页显示订单编号；客服不可见审批按钮
    tags: query,permission,readonly
```
