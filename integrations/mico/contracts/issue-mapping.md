# MiCo Issue ↔ Crosscheck Task 状态映射

MiCo Issue 是"协作投影"，Crosscheck Task 持有执行真相。回写时按下表映射，不要让 Issue 状态反向驱动 Task 状态。

| MiCo Issue 状态 | Crosscheck Task `state` | 说明 |
|---|---|---|
| Backlog / Created | `created` | 任务已创建，尚未执行 |
| In Progress | `running` | 任务执行中 |
| Blocked | `blocked` | 被环境/门禁阻塞，需人工介入（见 `result.error` 与事件） |
| Review | `completed`（待审） / reporting | 执行结束，等待人工复核报告与结论 |
| Done | `completed`（已审） | 报告已复核、结论确认 |
| Cancelled | `cancelled` | 任务被取消 |

## 回写规则

- 状态只能由 Task 真相推导，Agent 不得凭判断把 Issue 直接置为 Done。
- `completed` 不等于"全部用例 PASS"。`plan` 的 completed 仅表示出了计划；`run` 的通过情况看 `progress` 与报告。
- `blocked`/`failed` 必须如实回写为阻塞/失败，并附脱敏原因，不得静默置为 Review/Done。
- 一次任务可能多次执行（`attempts`）；回写以最新 `state`/`updated_at` 为准。

## Issue metadata 建议键

见 `../examples/issue-metadata.example.json`。只写标识与受控引用，不写秘密与完整报告正文。
