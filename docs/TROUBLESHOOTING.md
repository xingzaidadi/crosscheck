# 故障诊断

## 安装与浏览器

- `crosscheck doctor` 报依赖缺失：重新安装 wheel 或执行 `python -m pip install -r requirements.txt`。
- Chromium 缺失：执行 `python -m playwright install chromium`，然后再次运行 `crosscheck doctor`。
- 先运行 `crosscheck demo --workspace <目录>`；本地演示失败时不要接真实系统。

## 登录失效

- 删除对应 workspace 下 `.auth/<site>.json` 后重新执行登录。
- SSO/MFA/验证码使用 `login.mode: manual`，不得把 Token、密码或 Cookie 粘贴到对话或套件文件。
- 若登录后仍被打回登录页，检查 `liveness_url` 和 `logged_in_selector`。

## UI 找不到元素

- 优先重新录制 page model，使用标签、角色和可见文本，不固定易变 class。
- 检查页面是否位于 iframe、Shadow DOM 或 Canvas；这些场景需要专用插件或 PoC。
- 发布门禁中 Chromium 不可用会直接失败，不再把 UI 测试跳过当成成功。

## API 或抓包错误

- 检查 `url_pattern` 是否命中过宽或过窄。
- 确认写接口确实由 UI 动作触发；只抓到查询 POST 不能作为写入证据。
- 401/403 先刷新登录态；404 检查环境 base URL 和路由版本。

## 数据库无权限

- 查询使用只读账号；造数和清理使用独立最小权限写账号。
- 内置正式支持 MySQL；其他数据库不得直接套用 MySQL 元数据 SQL。
- DB 不可用时需要 DB 证据的用例必须 BLOCKED/ENV_ERROR，不能降级为 PASS。

## 清理失败

- 立即停止相同写入范围的后续测试。
- 根据 marker 和 cleanup registry 人工核对残留；不要直接清空整表。
- 修复清理配方并确认残留归零后，使用新 run id 重跑。

## 映射或知识未审批

- pending、stale、conflicted 的知识不能进入正式执行计划。
- 修改用例、连接器、身份或业务规则后必须重新计算内容哈希并审批。
- readiness 报告中的缺口没有关闭前，用例只能保持 DRAFT/BLOCKED/INVALID_SPEC。

## 发布失败

- 正式 `crosscheck release` 要求 Git 工作树干净。
- 本地候选验证可以使用 `--allow-dirty`，该包的 manifest 会标记 `dirty_build: true`，不得对外交付。
- 发布产物必须同时交付 ZIP、`.sha256`、`RELEASE_MANIFEST.json` 和对应 Git commit。
