# UI-first 测试框架交接说明

## 1. 用户初衷

用户希望把一份业务测试用例直接交给框架，并只补充真正必要的测试环境信息，框架负责完成 UI 测试，而不是要求用户理解或预先制作内部 binding。

目标流程：

```text
用例文件 + 测试环境 + 登录态/账号 + 必要测试数据
→ 解析 UI 用例
→ 自动识别页面入口、动作和预期
→ 复用登录态或完成登录准备
→ 打开真实浏览器
→ 执行 UI 操作
→ 对页面状态、字段、按钮、跳转和展示结果做业务断言
→ 保存截图、HTML、完整录屏、请求诊断和运行日志
→ 输出 UI 技术结果与业务验收结果
```

用户不应该被要求提供：

- binding；
- execution_ready；
- 内部 page model；
- 内部 oracle binding；
- 框架内部的执行计划格式。

这些都应该由框架在拿到用例后自动生成或自动判定。

## 2. 当前正确的执行原则

当前阶段明确是 **UI-first / UI-only**：

- 先做 UI 测试；
- API、DB、MQ、BPM 对账暂不作为本阶段执行结果；
- 浏览器捕获到的网络请求只能作为 UI 诊断证据，不能被报告成 API 测试通过/失败；
- UI 不能完成时，报告必须明确是 `BLOCKED`、`INCONCLUSIVE`、`ENV_ERROR` 或 `DEFERRED`；
- 只有 UI 动作真实执行、UI 断言真实执行、证据完整时，才允许 UI `PASS`。

## 3. 本次待测项目输入

### 用例

```text
C:\Users\MI\Desktop\易购资料\全球易购-需求管理及需求受理-测试用例-20261104.xlsx
```

已确认：该 Excel 共 142 条用例，编号 `TC01` 至 `TC142`。

### 被测系统

| 系统 | 站点键 | 入口 | 用途 |
|---|---|---|---|
| 需求管理/需求受理 | `ebuy-demand` | `https://migou.test.mioffice.cn/purchase/demand/management` | 主被测系统，142 条用例 |
| 受理台 | `ebuy-demand` | `https://migou.test.mioffice.cn/purchase/demand/accept` | 受理类操作页 |
| BPM 审批门户 | `bpm` | `https://bpm-infra.test.mioffice.cn` | 审批通过/驳回，独立域 |
| work.test | — | `https://work.test.mioffice.cn` | BPM 任务驳回接口，`POST /runtime/api/v1/task/reject` |

### 数据库

`db.yaml` 键：`ebuy_demand`

用途：需求库读写。

关键表：

- `demand_request`：主表、状态；
- `demand_request_item`：明细、汇率、BR 字段；
- `demand_item_assignment_record`：受理人；
- `demand_item_execution_node`：执行节点；
- `demand_request_item_template`；
- `demand_request_process`：BPM key。

数据库属于后续 API/DB 阶段，本阶段不能混入 UI 结果。

### 已核实的真实单据

| 单号 | 用途 | 备注 |
|---|---|---|
| `REQ2026110900159` | 汇率对账，TC40 | JPY 汇率 `0.042419`，`cny_amount=47.59` |
| `REQ2026111000052` | TC26 BPM 驳回 | 现成审批中单，fork 实测通过 |
| `REQ2026111000031` | TC25 主链路 | `PURCHASE_RETURN` 态，受理人 `lijie16/xuzhijun` |

### 账号与登录态

- 主账号：`liusixing`，来源为 `credentials.yaml`，默认造单/提交身份；
- 受理人：按 `demand_item_assignment_record.assignee_user_id` 动态查询；
- 已知受理人：`lijie16`、`xuzhijun`、`zhangjing40`；
- 审批人：动态从 `/approval-records/{bk}` 查询 `operation=null` 节点；
- BPM 独立 session：`workspace/.auth/bpm.json`；
- 主系统 session：`workspace/.auth/ebuy-demand.json`；
- 受理相关 session：`workspace/.auth/ebuy-demand-accept.json`、`workspace/.auth/ebuy-accept-lijie16.json` 等。

### 外部系统现状

- BPM 审批已打通：
  - 通过：`GET /bpmtool/api/bpmThree/approve`；
  - 驳回：`POST /runtime/api/v1/task/reject`，目标 `work.test`；
- 下游执行完成事件未打通：只有消费口 `/x5/bpm/processFinish`，没有写入触发接口；TC32/TC34 属于 `NEEDS_TRIGGER`；
- SAP 汇率数据在库中可用；
- BR 预算数据在库中，但挂 BR 的旧单对测试用户 detail 可能 `404`；
- FDS 文件上传/导入/导出未完全打通，涉及预签名多步流程；
- MQ/异步消息没有环境触发入口。

## 4. 当前框架实现状态

已经具备：

- Excel/CSV/JSON 用例读取；
- Playwright 真实浏览器执行；
- 登录态复用；
- 页面截图；
- HTML 保存；
- 浏览器视频录制底座；
- 网络请求捕获；
- UI 技术结果与业务验收结果分层；
- UI-only 入口：

```text
python crosscheck_cli.py ui-test \
  --cases <cases.xlsx/csv/json> \
  --url <测试环境 URL> \
  --workspace workspace \
  --session workspace/.auth/ebuy-demand.json
```

已经做过真实浏览器验证：本地页面中自动点击按钮、验证页面文字、生成截图和 HTML，相关测试通过。

## 5. 上一轮全量执行的事实与问题

执行命令：

```text
python crosscheck_cli.py ui-test \
  --cases workspace/input-cases.xlsx \
  --url https://migou.test.mioffice.cn/purchase/demand/management \
  --workspace workspace \
  --session workspace/.auth/ebuy-demand.json \
  --run-id full_ui_20261118
```

结果统计：

- `BLOCKED`: 42；
- `INCONCLUSIVE`: 35；
- `DEFERRED`: 65；
- `PASS`: 0；
- `FAIL`: 0；
- `ENV_ERROR`: 0。

但是这份报告 **不能作为正式报告交付**，原因如下：

1. 报告中虽然运行目录里实际存在 `.png` 和 `.webm` 文件，但 HTML 报告没有按框架要求正确展示和链接截图、录屏；
2. `BLOCKED` 用例没有浏览器执行，因此没有截图、录屏、HTML 等证据，这是安全隔离结果，但报告必须明确标注“未执行、无运行证据”，不能伪装成完整 UI 测试报告；
3. 报告自定义格式与框架已有报告格式不一致，证据字段没有统一为框架标准结构；
4. 报告中网络请求信息太突出，容易让人误认为本轮做了 API 测试；
5. 一些自然语言用例被粗略提取成无效动作，如把“详情只读展示”整体当成一个点击目标；
6. 业务断言覆盖率不足时虽然没有误报 PASS，但没有把“已执行 UI 步骤、未执行 UI 断言、缺少什么输入”展示得足够清楚。

因此，上一份 `full_ui_20261118/report.html` 只能作为调试产物，不能作为正式验收报告。

当前产物位置：

```text
workspace/reports/ui-tests/full_ui_20261118/
```

## 6. 下一步必须一次性解决的事项

### A. 先修正式 UI 报告，不再生成伪报告

每条 UI 用例必须包含：

- 用例 ID、标题、原始步骤、原始预期；
- UI 执行状态；
- 每一步动作的定位、执行结果、失败原因；
- UI 断言明细；
- 业务断言覆盖率；
- 截图列表及 HTML 内嵌/可点击预览；
- 完整录屏链接及 HTML `<video controls>`；
- 页面 HTML；
- 可选的网络诊断，且标题必须是“UI 诊断”，不能叫 API 结果；
- 明确标记：API 未执行、DB 未执行。

所有相对证据路径必须相对于 run 目录，禁止把绝对本机路径直接写进 HTML。

### B. UI-only 执行必须真正识别 UI 场景

不能只用“文本里出现页面/点击”做粗分类。需要结合：

- 用例步骤；
- 用例模块；
- UI 入口 URL；
- 已有历史 page model；
- `workspace/config/case_routes.yaml`；
- 既有 `workspace/_archive_specs/specs_accept` 和历史运行资产。

非 UI 用例必须进入 `DEFERRED`，但不能被当成 UI 失败。

### C. 只读 UI 用例优先自动建模

优先完成：

- `TC115`：状态页签默认待处理；
- `TC116`：列表多条件筛选；
- `TC117`：详情只读展示；
- `TC122`：页签切换保留筛选、重置分页；
- `TC124`：权限数据可见性；
- `TC137`：明细分页和状态筛选；
- `TC118`：导出按钮与异步通知，若页面可触发。

这些用例需要从实际页面 DOM 和真实列表数据生成动作，不应把整句业务描述当成一个控件文本。

### D. 输入缺失时只向用户索取真正业务信息

框架可以自动解决：

- binding；
- 页面模型候选；
- 控件定位候选；
- replay；
- 截图/录屏；
- UI 断言候选。

只有以下信息缺失时才询问用户：

- 测试环境 URL；
- 登录态或测试账号；
- 指定角色；
- 需要的真实单据/业务数据；
- 写入/审批是否允许在非生产环境执行；
- 异步 MQ/BPM 触发入口。

## 7. 新窗口建议直接使用的开场目标

```text
继续处理 vendor-test-agent。目标不是继续解释 binding，而是完成真正的 UI-first 产品闭环：

1. 用户给 Excel 用例、测试环境 URL、登录态和必要输入；
2. 框架自动识别 UI 用例并执行真实浏览器操作；
3. API/DB 在 UI 阶段只标记 NOT_EXECUTED，不得混入 UI 结果；
4. 每条用例必须有真实截图、完整录屏、HTML、动作回放结果和业务断言覆盖率；
5. 正式 HTML/JSON 报告必须链接和展示截图、录屏，不能只在目录里生成文件；
6. 不允许无证据 PASS；
7. 先把 TC115/116/117/122/124/137 这类只读 UI 用例做成真实可判定执行，再扩展写入/审批 UI 用例。
```

