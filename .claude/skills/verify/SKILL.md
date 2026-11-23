---
name: verify
description: 提交/交付前的冒烟自检 harness。改了 core/ 下的框架代码、或要提交 crosscheck 本身时，先跑这套确定性验证（离线回归 + 依赖预检 + 可选门禁），零新错误再交。触发场景：用户说"提交前验证一下/verify/交付前自检/这个改动能提交吗/跑一下冒烟"。不触发：跑业务用例（用 crosscheck）、只改 workspace 业务数据、与框架代码改动无关的闲聊。
---

# verify：框架改动的提交前冒烟自检

你是 crosscheck 框架的**提交前验证门**。依据 Claude Code 团队的验证方法论："验证=真跑"，且"**便宜的检查先跑**，开 PR 前先跑测试/构建/lint"。本 skill 把这套固化成一条确定性流程，**改了框架代码就该在提交前自动用它**，不要把半验证的工作交回去。

## 铁律（别违背初衷）

1. **这是框架自检，不是业务验证**。它验证的是 crosscheck 这个工具本身（`core/` / `tests/`），不是被测系统。跑业务用例请用 `crosscheck`。
2. **零新错误/警告才算过**。输出必须干净——没有新的报错、没有新的警告、没有 flaky。有一个红就是没过。
3. **不许作弊式"修绿"**：不许跳过失败测试、不许加 `sleep`、不许重试到过。flaky 找不到根因就**删掉并写明原因**（符合原文对 flaky 的处理）。
4. **按改动范围只跑该跑的**：小改动跑对应子集，碰到执行核心（`pipeline_runner` / `executor` / `circuit_breaker` / `suite_compiler` / gates）必须跑全量。

## 流程（便宜的先跑）

### 第 1 步：依赖/环境预检（最便宜）
```powershell
python crosscheck_cli.py doctor
```
确认 Python、依赖、Chromium 就绪。失败先修环境，别往下跑。

### 第 2 步：离线全量回归（核心冒烟）
```powershell
python run_tests.py
```
或等价的：
```powershell
python -m pytest -q
```
这是本工具的冒烟 harness，必须干净通过。碰到执行核心的改动，这一步**不可跳过**。

### 第 3 步（按需）：统一质量门禁
只有当改动影响 readiness / 资产 / 门禁判定逻辑时，对一个已有套件跑一次门禁，确认判定没被破坏：
```powershell
python crosscheck_cli.py quality-gate --suite workspace/suites/<suite-id> --workspace workspace
```
POC 期可按 `docs/QUALITY_GATE.md` 放宽门槛，但放宽要写进流水线配置，不改报告含义。

### 第 4 步：按改动范围的定向检查（可选，加速定位）
- 改了熔断：`python -m pytest tests/test_circuit_breaker.py tests/test_circuit_breaker_handoff.py tests/test_pipeline_breaker.py -q`
- 改了资产健康/重认证：`python -m pytest tests/test_asset_health.py tests/test_asset_recertification.py -q`
- 改了用例编译/执行：`python -m pytest tests/test_pipeline_runner.py tests/test_suite_*.py -q`

## 判定与交回

- **全绿、输出干净** → 可以提交/交付。在提交信息里简述验证了什么（对应原文的"commit 验证戳"思想）。
- **有红或有新警告** → **不要交回**。先定位根因修复（必要时用 `superpowers:systematic-debugging`），再从第 1 步重跑。
- **同一失败连修 3 轮仍不过** → 停手，转人工，说明卡在哪（对应原文的 3 轮熔断）。

## 与 maker/checker 的衔接

碰执行热路径的改动（`pipeline_runner` / `executor` / `circuit_breaker` 等），verify 通过后，**再派一个独立 agent 做对抗性代码评审**（写代码的 agent 不评审自己的产出）——这是原文强调的 maker/checker。可用 `superpowers:requesting-code-review` 或独立 `code-reviewer` agent。
