# 验证说明（阶段一）

本目录不含自动化测试，只记录**如何手动复现**阶段一 PoC 已验证的两条路径。所有命令均在 Crosscheck 主仓库内、针对一个**独立非生产 workspace** 执行，不访问任何业务生产系统。

示例一律使用中性占位符：workspace 用 `C:\crosscheck-workspaces\<project>`，suite 用 `suites/<suite-id>`。请替换为你自己的非生产目录与套件，切勿把业务 workspace、账号、登录态或真实报告放入本仓库。

## 前置

```powershell
pip install dist\crosscheck_agent-0.3.0-py3-none-any.whl
python -m playwright install chromium
crosscheck doctor   # 必须输出 OK: ... 依赖和 Chromium 均可用
```

> 注意：`crosscheck task` 子命令后不要加 `--pretty`（当前 CLI 的 REMAINDER 透传会把它误判为未知参数）。需要美化自行 `python -m json.tool`。

## 路径 A：只读 plan 闭环（预期 completed）

针对一个含 `suite.yaml` 的 canonical 套件，`operation: plan` 只评分并生成执行计划，不触碰实时系统。

```powershell
crosscheck task create --file examples\task.readonly.example.yaml --execute
crosscheck task status <task_id> --workspace <workspace>
crosscheck task events <task_id> --workspace <workspace>
```

预期：

- `state = completed`，task CLI 退出码 `0`。
- events 依次为 `created → running → completed`。
- 产物：`<suite>/reports/suite_score.json`、`<suite>/reports/execution_plan.json`。
- 若套件评分 `ready=0`，说明用例缺 UI/API/DB 断言，这是**真实覆盖缺口**，应如实报告为缺口，不得描述为通过。

## 路径 B：ready=0 套件的 run（预期 blocked，而非 failed）

对一个没有任何 approved READY 用例的套件执行 `operation: run`：

```powershell
# task 文件中 operation: run，suite 指向 ready=0 的套件
crosscheck task create --file <run.task.yaml> --execute
```

预期（本轮已实测）：

- `state = blocked`，`result.status = blocked`，task CLI 退出码 `4`，底层 `run_suite` 退出码 `2`。
- `result.error = [suite] 没有可执行的 approved canonical case。`
- Agent 必须把它报告为 **blocked：没有 approved READY case**，不得解释为测试失败，不得绕过审批，不得自行把 draft 用例改成 READY。

## 常见坑

- 必须使用装有 `yaml`/`playwright`/`sqlalchemy` 依赖的 Python 解释器。若 `import yaml` 报错，说明选错了解释器（例如宿主自带的精简运行时），换成安装了 wheel 依赖的解释器即可。
- `task status`/`task events` 必须带 `--workspace`；`task create` 可从 task 文件读取 workspace。
- `task_id` 在同一 workspace 内唯一，重复会被拒绝；复跑前先清理对应 `<workspace>/.crosscheck/tasks/<task_id>/`。
