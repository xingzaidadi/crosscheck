---
name: crosscheck
description: 在 MiCo 中编排 Crosscheck 企业 Web 测试引擎，完成测试任务的创建、执行、状态查询与脱敏结果回写。只要用户在 MiCo Issue 或对话中提到 Crosscheck 测试、回归验证、Excel/用例执行、UI/接口/数据库跨层对账、只读体检、失败重跑，或要求对某业务系统跑一轮测试并把结论回写 Issue，就使用本 Skill。Agent 只做编排与结果解释，PASS/FAIL 判定、断言、数据库清理一律由 Crosscheck CLI 完成，模型不得替代引擎下结论。
---

# Crosscheck for MiCo

本 Skill 是 Crosscheck 仓库内 `.agents/skills/crosscheck` 的 MiCo 版本。它只保留 MiCo Agent 需要的编排契约，不复制内部流水线实现细节。Agent 是编排者；`crosscheck` CLI 是唯一的确定性执行工具。

## 职责边界（必须遵守）

- 不得由模型判定 PASS/FAIL、代替引擎做断言或数据库对账；结论只来自 CLI 输出的 `state` 与报告。
- 不得直接修改 workspace 内的 checkpoint、`.crosscheck/` 任务存储、规格或知识库文件。
- 不得执行来源不明 workspace 中的 Python 脚本（不要使用 `--allow-workspace-scripts`）。
- 不得把凭据、Cookie、Token、数据库 DSN、完整抓包或完整报告正文回写 MiCo，详见 `contracts/security-boundary.md`。
- 遇到非生产确认缺失、需要人工登录、写入权限不足或安全门禁失败时，必须阻塞并一次性向发起人提问，不要绕过。

## 何时触发

Issue/对话出现以下意图之一即触发：新系统测试接入、回归、冒烟、Excel/CSV 用例执行、UI/API/DB 跨层验证、只读体检、对账、失败重跑、测试报告解读。仅"写代码/改 bug"而未要求跑测试时不要触发。

## 前置检查：安装

首次或环境不确定时先确认安装（不访问任何业务系统）：

```powershell
pip install crosscheck_agent-0.3.0-py3-none-any.whl
python -m playwright install chromium
crosscheck doctor
```

`crosscheck doctor` 必须输出 `OK: ... 依赖和 Chromium 均可用` 才算通过。失败时按其提示修复依赖或 Chromium，并把阻塞原因回报发起人。

## 选择 workspace 与 suite

- **workspace**：业务自管目录，放在产品仓库之外（例如 `C:\crosscheck-workspaces\<project>`）。秘密只存在于 `<workspace>/config/credentials.yaml`、`<workspace>/config/db.yaml`、`<workspace>/.auth/`。
- **suite**：必须是 workspace 内的 **canonical 套件目录**，该目录下含 `suite.yaml`。task 的 `suite` 字段写相对 workspace 的路径（如 `suites/<suite-id>`），且必须位于 workspace 内，否则 CLI 拒绝。
- 散文/Excel/CSV/JSON 用例不能直接跑，需先用 `scripts/import_suite.py` 导入为 canonical 套件（此步在 Crosscheck 仓库内完成，不在 MiCo 侧）。

## 生成 task 文件

task 文件是 YAML 或 JSON 对象，字段契约见 `contracts/task-result.schema.json`，只读模板见 `examples/task.readonly.example.yaml`。关键约束（与引擎一致）：

- `operation`：**只能是 `plan` 或 `run`**。`plan` = 评分并生成 canonical 执行计划，**不触碰任何实时系统**（纯只读，首选的安全验证）；`run` = pilot 后执行当前 READY 用例。
- `task_id`：匹配 `^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$`，在同一 workspace 内唯一；重复会被拒绝。
- `workspace`：绝对路径；必须与执行时 `--workspace` 一致。
- `suite`：workspace 内 canonical 套件目录（含 `suite.yaml`）。
- `scope.cases`：用例 id 列表，空列表表示全部；也可用 `scope.only`。
- `execution`：`pilot_size`(int)、`ensure_login`(bool)、`resume`(bool，`false` 才加 `--no-resume`)、`run_id`(可选)。
- `authorization`：`confirmed_non_production`、`allow_write` 为**随任务持久化的声明性元数据**；真正的非生产与写入安全门禁由 `suite.yaml` 的 `authorization` 和引擎写入门禁强制，不由此字段决定。详见 `contracts/security-boundary.md`。

Agent 可以创建 task 文件，但不得写入或篡改 workspace 中既有的规格、知识库或任务存储。

## 运行 task

```powershell
crosscheck task create --file task.yaml --execute
crosscheck task status <task_id> --workspace <workspace>
crosscheck task events <task_id> --workspace <workspace>
```

- `--execute` 让 create 后立即执行；省略则只创建待执行任务，之后用 `crosscheck task run <task_id> --workspace <workspace>` 执行。
- 输出为单行 JSON（`task create/status` 输出任务对象，`task events` 输出事件数组）。**不要在子命令后面加 `--pretty`**（当前 CLI 的 REMAINDER 透传会把它误判为未知参数）；需要美化就自行用 `python -m json.tool` 处理 stdout。
- `status`/`events` 必须带 `--workspace`；`create` 可从 task 文件读取 workspace。

## 解释状态

读取 `state` 字段，不要臆断：

- `completed`：引擎正常结束（`plan` 出计划，`run` 跑完 READY 集）。是否"测试通过"看 `run` 报告与 progress，不等于全部 PASS。
- `blocked`：被门禁或环境阻塞（如需要人工登录、写入门禁、缺 READY 用例、清理失败）。停下来，读 `result.error` 与事件，一次性向发起人汇报阻塞项，不要自行绕过。
- `failed`：执行失败。读 `result.exit_code`、`result.log_path` 定位，不要把失败说成通过。
- `created`/`running`/`cancelled`：分别为已创建未执行、执行中、已取消。

task CLI 退出码：`0` 正常（created/running/completed/cancelled），`4` blocked，`1` failed，`2` 参数或校验错误。

READY 缺口（如套件评分 `ready=0`、缺 UI/API/DB 断言）是**真实的覆盖缺口**，应如实报告为缺口/阻塞，不得描述为通过，也不得描述为"仅 API 结果 = 三层验证"。

## 回写 MiCo

- 只回写：`task_id`、`state`、`stage`、progress 数字（total/ready/executed/passed/failed）、**脱敏**的失败原因、以及报告的受控链接或路径引用。
- Issue 状态映射见 `contracts/issue-mapping.md`；Issue metadata 字段见 `examples/issue-metadata.example.json`。
- 禁止回写内容与完整清单见 `contracts/security-boundary.md`：凭据、Cookie、Token、DSN、完整请求头、完整抓包、完整报告正文一律留在本地 workspace。

## 何时必须阻塞人工

- 目标环境未明确确认为非生产；
- 需要人工登录 / SSO / 验证码 / 2FA；
- 涉及写入但缺少独立低权限写账号、缺 `cleanup`/`allowed_tables`，或规格未 `human_verified`；
- 需要执行 workspace 内脚本但来源未经发起人确认；
- 出现知识冲突（新答案与已 approved 知识矛盾）。

以上任一成立时，停止相关正式验收，一次性汇报，等待发起人指令。

## 参考

- task 字段与返回契约：`contracts/task-result.schema.json`
- Issue 状态映射：`contracts/issue-mapping.md`
- 数据与安全边界：`contracts/security-boundary.md`
- 只读 task 模板：`examples/task.readonly.example.yaml`
- PoC 验收清单：`docs/poc-acceptance.md`
- 下一阶段 MCP 工具设计稿（尚未实现）：`docs/mcp-tool-design.md`
