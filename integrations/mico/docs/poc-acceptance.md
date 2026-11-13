# 阶段一 PoC 验收清单

目标：验证一条真实的测试闭环能通过 MiCo Agent 编排 Crosscheck 完成，且不泄露敏感数据。

> 说明：本文用中性占位符描述。`<crosscheck-repo>` 指 Crosscheck 主仓库目录，`<workspace>` 指独立非生产测试 workspace，`<suite-id>` 指其中一个 canonical 套件目录。业务 workspace、套件业务名、账号、登录态与真实报告不放入本仓库。

## 必须完成项（本轮状态）

| # | 验收项 | 状态 | 证据 |
|---|---|---|---|
| 1 | Skill 可被 MiCo 导入 | ✅ | `skills/crosscheck/SKILL.md`，`mico skill import --file ...` 成功 |
| 2 | Agent 可绑定该 Skill | ⚠ 阻塞 | Agent 已创建；绑定命令因权限 `You do not have permission to access this resource` 被拒，已原样交管理员，未绕过（见下方命令） |
| 3 | Agent 能生成合法 task YAML | ✅ | `examples/task.readonly.example.yaml`，字段契约见 `contracts/task-result.schema.json` |
| 4 | `crosscheck task create` 成功 | ✅ | 只读任务 `create --execute` 返回任务对象，退出码 `0` |
| 5 | `task status` / `task events` 成功 | ✅ | status=`completed`；events=`created → running → completed` |
| 6 | 对 ready=0 套件正确报告 blocked | ✅ | `operation: run` → `state=blocked`、CLI 退出码 `4`、`result.error=[suite] 没有可执行的 approved canonical case。`（对应「blocked：没有 approved READY case」） |
| 7 | 不把 blocked 当测试失败 | ✅ | SKILL「解释状态」明确区分 blocked / failed；本轮 ready=0 判为 blocked 而非 failed |
| 8 | 不绕过审批、不自行把 draft 改 READY | ✅ | 未使用任何绕过手段；draft/READY 由引擎与 `suite.yaml` 授权决定 |
| 9 | 不泄露账号 / Cookie / DSN / 业务数据 | ✅ | 仅回写标识、progress、脱敏缺口；禁写清单见 `contracts/security-boundary.md` |

## 有条件完成项（需 ≥1 个 approved READY 只读用例后才做）

| 验收项 | 状态 | 说明 |
|---|---|---|
| `crosscheck task run/continue` 实时执行并出报告 | ⬜ 未达触发条件 | 当前套件 `ready=0`，无 approved READY 用例；须先补齐断言、确认非生产与可用登录方式，再在非生产确认下执行 |

## 本轮真实运行结论

### 只读 plan（已验证 completed）

- 对一个含 `suite.yaml` 的 canonical 套件执行 `operation: plan`：`state=completed`，退出码 `0`。
- 套件评分 `ready=0`：全部用例缺 UI/API/DB 断言，被引擎如实判为**未 READY（覆盖缺口）**——这是真实缺口，不是通过。
- 产物：`<suite>/reports/suite_score.json`、`<suite>/reports/execution_plan.json`、任务存储 `<workspace>/.crosscheck/tasks/<task_id>/`。

### ready=0 套件的 run（已验证 blocked）

- 对同一 `ready=0` 套件执行 `operation: run`：`state=blocked`、`result.status=blocked`、task CLI 退出码 `4`、底层 `run_suite` 退出码 `2`。
- `result.error=[suite] 没有可执行的 approved canonical case。`
- Agent 正确报告为 **blocked：没有 approved READY case**，不解释为测试失败，不绕过审批。

## 待管理员执行（Skill ↔ Agent 绑定，权限阻塞项）

```bash
mico agent skills add --agent-id <crosscheck-agent-id> --skill-ids <crosscheck-skill-id> --output json
```

当前运行身份缺少该资源写权限，故未绑定；请以有权限的账号执行，或授予该 Agent 绑定权限后重试。

## 下一步

1. 补齐 READY 用例（断言）、确认非生产与登录方式后，再做「有条件完成项」的实时执行。
2. 阶段二：实现 `crosscheck_mcp`（见 `mcp-tool-design.md`），用类型化高层工具替代直接 CLI 调用。
