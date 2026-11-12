# Pipeline Mode

## 状态机

```text
INIT
  → CONTEXT_DISCOVERED
  → INSTALL_READY
  → WORKSPACE_READY
  → PREFLIGHT_READY
  → SESSION_READY
  → DRY_RUN_READY
  → PILOT_RUNNING
  → PILOT_REVIEWED
  → FULL_RUNNING
  → REPORT_READY
```

任一阶段如果遇到硬门禁，转为 `BLOCKED`；如果是可重试的网络/浏览器临时错误，自动重试一次；如果是业务 FAIL，不自动重复写入动作。

## 自动判断规则

### 上下文发现

按优先级读取：

1. 当前用户消息和前序确认；
2. 当前项目路径；
3. `VTA_WORKSPACE`；
4. workspace 下的 profiles、cases、knowledge_base、runs；
5. 最近修改的用例文件；
6. profile 中的 site、base_url、login.mode、db 和 defaults。

只记录“已配置/未配置/可用/不可用”，不要输出秘密值。

### 默认选择

- 只有一个有效 profile：自动选择它。
- 有多个 profile 且用户未指定：优先最近使用、已有有效 session 且有用例匹配的 profile；仍无法判断才提问。
- 有多个用例文件：优先用户刚提到的文件；否则优先最近修改的 `.xlsx`；仍有同时间候选才提问。
- 未指定执行范围：preflight → session check → dry-run → 最多 3 条 pilot → 自动执行全部 READY 用例。
- 用户说“测试这批用例”“继续测试”“完整回归/全部用例”：pilot 通过后自动进入 READY 批量执行，不再询问。
- 只有用户明确说“仅试跑”“先看看能不能用”“只跑 N 条/指定编号”时，才在限定范围后停止。

### 登录

- 已有 session 且 preflight 检查有效：继续，不重复登录。
- profile 是 credential 模式且本地凭据字段齐全：自动登录；失败一次后停止并报告，不反复尝试。
- profile 是 manual、SSO、验证码或 2FA：只有必须人工操作时才提问，请用户完成后继续，不提前询问“是否要登录”。
- 用户明确要求重新登录：直接使用 `--force`，不再询问。

### 写入和清理

- 查询/对账优先自动执行。
- 写入规格没有 `human_verified`、`cleanup` 或 `allowed_tables`：跳过写入，继续执行可安全的查询类用例，并在报告中列出阻塞项。
- 有完整写入门禁且用户已确认非生产和测试账号：按 pilot 执行，默认清理。
- 清理失败：停止扩大范围，保留 marker 和报告路径，要求先处理残留。

### 自动扩批

pilot 通过且环境/清理安全时：

1. 从 `suite_plan` 和规格中筛选 `human_verified && !blocked` 的 READY 集合；
2. 排除覆盖层缺失且会导致错误结论的规格；
3. 查询类可按配置并发执行；
4. UI、写入和流程类串行执行；
5. 每条完成后记录报告，但不等待用户回复；
6. 业务 FAIL 继续其他独立用例；
7. 清理失败、环境整体不可用、连续 3 条同类 `ENV_ERROR` 时熔断。

不要把“批量执行”解释成强行执行 draft/blocked 用例。批量范围始终是当前 READY 集合，缺口项进入报告。

### 提问条件

只有下列情况才提问：

- 无法确定测试环境是否为非生产环境；
- 多个 profile/用例候选无法安全选择；
- 需要人工登录、验证码、2FA 或 SSO；
- 写入所需测试账号、清理目标或允许表无法确认；
- 用户要求执行不可信 workspace 脚本；
- 目标文件不存在、损坏或需要覆盖现有业务文件；
- 结果需要业务口径判断，工具无法确定。

一次提问必须汇总当前阶段全部阻塞项。不要问“现在继续吗”。用户给出一批用例并要求测试，即视为授权执行当前 READY 集合；只有新的不可逆操作、生产风险或硬门禁才提问。

## 进度输出

开始时输出一行计划，例如：

```text
我会自动执行：安装预检 → workspace 检查 → 环境预检 → 登录态检查 → dry-run → 3 条试跑 → 全部 READY 用例；只有遇到硬门禁才询问。
```

阶段完成时用一行更新，不等待确认：

```text
[3/6] 环境预检通过：DB/API/站点均就绪，继续检查登录态。
```

阻塞时输出：已完成阶段、阻塞原因、需要用户提供的最少信息，以及回答后会自动继续的阶段。

## 运行策略

- 使用 Agent 的计划工具跟踪阶段，但不要把每个阶段变成用户确认点。
- 命令失败先读取 stderr、退出码和报告，不要盲目重复。
- 运行结果优先从 `workspace/runs/<run-id>/` 和结构化 JSON 读取。
- 始终在最终报告中列出未执行的范围及原因。
