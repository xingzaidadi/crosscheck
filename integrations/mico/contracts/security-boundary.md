# 数据与安全边界

原则：**执行真相与敏感数据留在本地 workspace，MiCo 只收到标识、进度与脱敏结论。** MiCo 凭据作用域属于运行时 owner，不因本集成而扩大可读写范围。

## 绝不回写 MiCo（留在本地 workspace）

- 账号口令、密码：`<workspace>/config/credentials.yaml`
- 数据库连接 / DSN / 库口令：`<workspace>/config/db.yaml`
- 登录态 / Cookie / Token：`<workspace>/.auth/`
- 完整请求头、完整抓包样本：`<workspace>/captures/`
- 完整 HTML 报告正文、录像、截图原件:`<workspace>/artifacts/`、`<suite>/reports/`
- 任意包含上述内容的日志片段（回写前必须脱敏）

## 允许回写 MiCo

- `task_id`、`state`、`stage`
- progress 数字：total / ready / executed / passed / failed
- **脱敏后**的失败原因（去除 URL 参数、主机名、账号、堆栈中的敏感路径）
- 报告的受控链接或路径引用（不是报告正文）
- `run_id`、`cleanup_status` 等执行元数据

## 执行期硬门禁（不得绕过）

- 目标环境未确认非生产 → 阻塞提问，仅凭域名猜测不算确认。
- 需要人工登录 / SSO / 验证码 / 2FA → 阻塞，不代填凭据。
- 写入用例：须独立低权限写账号、`cleanup` 非空且仅含预期目标、`allowed_tables` 非空、规格 `human_verified`、默认启用清理。缺一即阻塞。默认禁止 `--no-cleanup`。
- 默认禁止 `--allow-workspace-scripts`：workspace 脚本不是沙箱，来源未经发起人确认不得执行。
- 不要求用户在聊天/Issue 中粘贴任何秘密；秘密只写入本地 workspace 配置。

## 关于 task 文件的 authorization 字段

`task.yaml` 的 `authorization.confirmed_non_production` 与 `allow_write` 是**声明性元数据**，随任务持久化，便于审计。它们**不是**真正的执行门禁——实际的非生产确认与写入安全由 `suite.yaml` 的 `authorization` 块和引擎（`run_suite`）的写入门禁强制。因此：

- 不要因为在 task 文件里写了 `confirmed_non_production: true` 就认为环境已被授权；真正依据是 suite 的授权与发起人确认。
- 只读 `operation: plan` 不写入任何实时系统，是最安全的默认验证路径。
