# Crosscheck × MiCo 集成

把 Crosscheck（Python 企业 Web 测试引擎）接入 MiCo（Agent/Skill/Issue/Workflow/Autopilot 平台）。本目录属于 Crosscheck 主仓库；MiCo 侧通用集成资产集中在此，`finance-openclaw-rpa` 等业务仓库只作被测项目或调用方，不承载通用 Skill/MCP。

## 原则

- MiCo Issue 是"协作投影"，Crosscheck Task 持有执行真相。
- Agent 只编排与解释，PASS/FAIL、断言、清理一律由 `crosscheck` CLI 完成。
- 敏感数据留在本地 workspace，MiCo 只收标识、进度与脱敏结论。

## 目录

```text
integrations/mico/
├── README.md                       本文件
├── skills/crosscheck/SKILL.md      MiCo 版 Crosscheck Skill（可导入 MiCo）
├── examples/
│   ├── task.readonly.example.yaml  只读 task 模板（operation: plan）
│   ├── mcp-config.example.json     阶段二 MCP 配置样例（设计稿，未实现）
│   └── issue-metadata.example.json Issue metadata 建议键
├── contracts/
│   ├── task-result.schema.json     task 输入字段与返回对象契约（源自 core/task）
│   ├── issue-mapping.md            Issue 状态 ↔ Task state 映射
│   └── security-boundary.md        数据与安全边界、执行期硬门禁
├── docs/
│   ├── poc-acceptance.md           阶段一 PoC 验收清单与本轮运行结论
│   └── mcp-tool-design.md          阶段二 MCP 工具与 crosscheck_mcp 模块设计稿（未实现）
└── tests/README.md                 验证说明：如何复现本轮只读闭环与 ready=0 阻塞判定
```

## 阶段一快速验证（只读）

```powershell
pip install dist\crosscheck_agent-0.3.0-py3-none-any.whl
python -m playwright install chromium
crosscheck doctor

crosscheck task create --file examples\task.readonly.example.yaml --execute
crosscheck task status <task_id> --workspace <workspace>
crosscheck task events <task_id> --workspace <workspace>
```

> 注意：子命令后不要加 `--pretty`（当前 CLI 的 REMAINDER 透传会误判）。需要美化自行 `python -m json.tool`。

## 导入到 MiCo

```bash
mico skill import --file integrations/mico/skills/crosscheck/SKILL.md --output json
```

导入后把该 Skill 绑定到 Crosscheck Test Agent（导入与绑定是两个动作）。

## 范围

- 本轮（阶段一）：Skill + Task CLI + 一个真实只读任务闭环 + 脱敏回写。
- 下一轮（阶段二）：实现 `crosscheck_mcp`，用类型化高层工具替代直接 CLI。
