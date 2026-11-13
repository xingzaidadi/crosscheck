# 阶段二 MCP 工具设计稿（尚未实现）

> 本文仅为设计稿。`crosscheck_mcp` 模块本轮**未实现、未验证**，下列模块划分与 `inputSchema` 均为拟定契约，不代表已存在的能力。

## 定位

用一组**高层、类型化**的 MCP 工具，替代让模型直接拼 CLI。底层动作（probe/login/plan/pilot/cleanup）由 Task Runtime 的状态机编排，不逐个暴露给模型。

`crosscheck_mcp` 是**通用 MCP Server**，放在 Crosscheck 主仓库，任何 MCP Host（MiCo、CI、其它 IDE）都能复用；MiCo 专属的 Skill/配置/契约留在 `integrations/mico/`，不进 `crosscheck_mcp`。

## 模块划分（拟定）

```text
crosscheck_mcp/
├── __init__.py      包元信息与公共导出
├── __main__.py      python -m crosscheck_mcp 入口，装配 server 并启动
├── server.py        MCP server 生命周期、工具注册、请求分发
├── tools.py         10 个高层工具的实现，内部调用 core/task 的 TaskService
├── schemas.py       各工具 inputSchema / 返回对象的类型定义（与 contracts 对齐）
└── security.py      workspace 白名单、路径越界拒绝、脱敏与秘密过滤
```

- `tools.py` 只经由 `core/task` 的 `TaskService` 编排，不自行拼 shell、不透传任意命令。
- `schemas.py` 与 `integrations/mico/contracts/task-result.schema.json` 保持同源，避免两处契约漂移。
- `security.py` 是唯一的出入口过滤层：入参做 workspace 白名单校验，出参做脱敏。

## 拟暴露的 10 个工具

```text
crosscheck_project_init
crosscheck_project_inspect
crosscheck_task_create
crosscheck_task_status
crosscheck_task_continue
crosscheck_task_cancel
crosscheck_approval_decide
crosscheck_run_retry
crosscheck_cleanup_run
crosscheck_report_get
```

## 示例：crosscheck_task_create（拟定）

描述：创建一个持久化 Crosscheck 测试任务。

```json
{
  "name": "crosscheck_task_create",
  "description": "创建一个持久化 Crosscheck 测试任务",
  "inputSchema": {
    "type": "object",
    "properties": {
      "workspace": { "type": "string" },
      "suite": { "type": "string" },
      "operation": { "type": "string", "enum": ["plan", "run"] },
      "pilot_size": { "type": "integer", "minimum": 0 },
      "ensure_login": { "type": "boolean" },
      "allow_write": { "type": "boolean" }
    },
    "required": ["workspace", "suite", "operation"]
  }
}
```

返回对象字段（与 CLI 任务对象一致）：`schema_version`、`task_id`、`state`、`stage`、`progress`(total/ready/executed/passed/failed)、`blockers`(每项含 `type`、`cases`)。

## 安全要求（阶段二落地时强制）

- workspace 白名单（`CROSSCHECK_WORKSPACE_ROOT`），拒绝越界路径，统一在 `security.py` 实现。
- 不暴露裸 shell，不透传任意命令。
- 不经 MCP 传递任何凭据；脱敏输出，禁止回传秘密与完整报告正文。
- 保持 Crosscheck Core / Task API 与宿主解耦，便于后续接入 CI 或其它 MCP Host。
