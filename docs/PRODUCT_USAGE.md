# Crosscheck 产品化使用说明

> 产品入口仅为 `crosscheck`。`run_*.py` 为历史迁移兼容脚本，新项目不要直接依赖。

首次安装先执行：

```powershell
crosscheck doctor
crosscheck demo --workspace ./crosscheck-demo
crosscheck init ./my-workspace
```

本地 demo 同时验证真实 Chromium 页面操作、HTTP API、SQLite 落库和 marker 清理；demo 不通过时不要接入业务系统。

## 定位

Crosscheck 是 AI Test Agent、确定性测试引擎、UI/API/DB 适配器和项目知识库组成的企业 Web 系统自主测试与跨层验证平台。Agent 负责理解和编排；引擎负责动作、断言、清理和结果判定。

## 新系统接入

首次接入推荐使用统一向导，它会生成 profile、版本化 UI Application Model 和可追踪 intake：

```powershell
crosscheck ui-onboard --system demo --url https://test.example.com --cases ./cases.xlsx --workspace ./workspace --role operator
```

UI 缺口审计现在同时生成可分派任务队列；录制资产必须按
`candidate → replay_verified → human_verified → approved → active` 晋级后才可正式执行：

```powershell
crosscheck ui-assets queue --workspace ./workspace
crosscheck ui-assets accept --workspace ./workspace --asset-id <id> --reviewer qa
crosscheck ui-assets activate --workspace ./workspace --asset-id <id> --reviewer qa-lead
```

UI-only 快速 Pilot：

```powershell
crosscheck ui-pilot --workspace ./workspace --cases ./cases.xlsx
```

它会自动匹配已有 suite、检查 UI readiness、复用 workspace 中的登录态，默认选择最多 3 条低风险只读 UI 用例，并生成 `reports/ui_pilot_latest.json`、截图、录像和 HTML 报告。API/DB 不在本轮执行范围内。

直接 URL + 原始用例入口：

```powershell
crosscheck ui-run --cases ./cases.xlsx --url https://test.example.com/list --workspace ./workspace
```

`ui-run` 默认按 URL 匹配 profile 并检活/复用登录态；失效时按 profile 的 `credential` 或 `manual` 模式刷新。候选 UI binding 和 oracle 会写入
`workspace/knowledge_base/asset_candidates/`，复杂或未确定的业务断言不会被自动判为通过。若需完全不触发登录刷新，显式使用 `--no-session-refresh`。

推荐使用可续跑的统一闭环入口：

```powershell
crosscheck flow --cases ./cases.xlsx --profile ./profile.yaml --suite ./workspace/suites/demo --workspace ./workspace
# 编辑首次输出的 gap_resolutions.template.yaml 后继续；复核通过后自动执行全部 READY
crosscheck flow --continue ./workspace/.crosscheck/flows/<flow-id> --resolutions ./gap_resolutions.yaml
```

该入口持久化 `state.json`，并持续更新 `unified_report.json` 和 `unified_report.md`。首次发现缺口时状态为
`WAITING_FOR_INPUT`；补充内容会按 `gap_id` 和审批身份复核，随后只执行 onboarding READY 与 canonical
execution-ready 的交集。未 READY 用例保留在统一报告中，不会被误报为通过。

1. 确保是测试或预发布环境，准备前端 URL、测试账号、API/OpenAPI、数据库只读账号和用例来源。
2. 执行 `crosscheck doctor` 检查安装。
3. 执行 `crosscheck init <workspace>` 创建业务 workspace。
4. 配置 profile、数据库和角色登录态。
5. 将 Excel/case-gen 输入导入 canonical suite，补齐 UI/API/DB 绑定、断言、数据配方和清理。
6. 执行 `crosscheck plan` 查看缺口，只有 READY 用例进入 Pilot。
7. 执行 `crosscheck run`，工具自动 Pilot、批量执行、证据归档和清理。

执行 `crosscheck dashboard --workspace <ws> --serve` 可在本机查看项目、套件、运行和知识状态；执行 `crosscheck map` 生成 UI/API/DB/状态统一系统地图；执行 `crosscheck readiness` 输出每条 canonical 用例的 READY 缺口和可复用知识建议。

## 知识闭环

遇到业务规则不确定时，先用 `crosscheck knowledge check-question` 检查是否已有答案；没有答案才询问用户。回答通过 `record-answer` 保存为 pending，审核后用 `approve`。正式用例使用 `knowledge_refs` 绑定知识，内容变化会让旧执行计划失效。

## 明确边界

Crosscheck 主要承担功能、集成、UI/API/DB 一致性、测试数据、清理和回归测试；不替代单元测试、专业性能测试、渗透测试、主观体验评价或产品规则决策。

正式兼容范围和条件支持项以 `docs/COMPATIBILITY.md` 为准；失败处理见 `docs/TROUBLESHOOTING.md`。
