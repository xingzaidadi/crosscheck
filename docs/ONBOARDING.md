# 接入一个新业务(零改框架码)

crosscheck 是通用测试框架:喂散文用例 → 自动建模 → 执行 → 出「页面↔接口↔库」多方验证报告。
**框架代码(`core/` `adapters/` `run_*.py`)零业务,一行不用改**;一个业务的全部东西(用例、库连接、登录态、映射、抓包、报告)都在它自己的 `workspace/` 目录里。接入新业务 = 建一个 workspace + 填配置。

## 0. 建骨架
```bash
python scripts/init_workspace.py /path/to/my-biz-workspace
```
之后所有命令加 `--workspace /path/to/my-biz-workspace`(或设环境变量 `VTA_WORKSPACE`,或把它命名为仓库根下的 `./workspace`)。

## 1. 配库连接 — `config/db.yaml`
从 `db.example.yaml` 复制,填只读库(查询/对账)和写库(造数/清理,独立测试账号;不填则拒绝写操作)。**不提交**(已 gitignore)。

## 2. 配站点与登录 — `profiles/<站点>.yaml`
从 `_example.yaml` 复制,填 `base_url` 和登录方式(A 人工登一次最稳 / B 声明式账密)。建登录态:
```bash
python run_verify.py login --profile <站点> --workspace <ws>
```
登录态存 `.auth/<站点>.json`,后续复用。

## 3. 配路由 — `config/case_routes.yaml`
从 `case_routes.example.yaml` 复制。它把用例路由到「功能」,框架据此自动建模。两类:

- **查询类**:给 `feature` + `db`。先探一次产映射草稿、人审:
  ```bash
  python run_verify.py probe --profile <站点> --feature <功能> --url "<列表页URL>" --table <主表> --workspace <ws>
  # 审 knowledge_base/query_mapping/<功能>.draft.json → 确认后另存为 <功能>.json
  ```
- **写入类**:给 `write` 块(接口/模板/表/预期状态)。接口和提交体**录一次写操作自动得**(prober `pick_write_call`);清理子表、标记字段**框架按库 schema/模板自动推导**,route 只需 `table` + 预期状态。状态流转类用 `data_prep` 先造前置单、`capture` 抓单号串给主动作。

## 4. 放用例、跑
把用例 Excel 放进 `cases/`,一条命令自动建模 + 执行:
```bash
python run_batch.py --excel cases/<用例>.xlsx --auto-model --workspace <ws>
```
框架给能建模的用例(有路由+映射/模板)自动拼规格并执行;复杂用例可让 **crosscheck 技能**读散文草拟规格(会话内 LLM)、人审一次转 `human_verified` 后再跑。

## 5. 看报告
每次运行一个文件夹 `runs/run_<时间戳>/`:`report.html` 详列每条用例——做了什么 / 预期 vs 实际 / 查了哪些库表+SQL / 截图 / 录像 / 清理是否销账。

## 机制保障(不用管,自动的)
- **数据隔离**:造数带唯一 marker,执行后按 marker 反删(子表按父单号),registry 兜底重试;diff 安全网拦未声明的表变更。
- **异步**:审批/事件翻转状态用轮询等待;事件消费可断言库事件表或外部通知网关。
- **UI**:复杂控件(级联/网格/日期)语义回放,选择器失效多策略自愈,全程截图+录像。
- **自进化**:字段知识按功能/站点累积(`knowledge_base/field_intel`),越跑越快。

## 红线
- 业务数据只进 `workspace/`(已 gitignore);**不要把接口地址/库表/账号写进 `core/`**。
- 写操作必须有清理 + `allowed_tables`;未人审的规格不执行。
