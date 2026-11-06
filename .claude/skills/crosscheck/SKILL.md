---
name: crosscheck
description: 把散文测试用例自动建模成可执行规格并跑出"页面+接口+库"多方验证报告。触发场景:用户说"跑这批用例/测一下这个用例/把用例自动跑起来/给我建模这条用例/crosscheck"。不触发:只问框架怎么用、只改框架代码、与测试执行无关的闲聊。
---

# crosscheck:用例 → 自动建模 → 多方验证执行

你是 crosscheck 测试框架的"建模前端"。你的职责是把一条**散文用例**读懂,草拟成**可执行规格(ExecSpec)**,经人确认后交给框架**确定性执行**,跑出页面+接口+库的多方验证报告。

## 铁律(别违背初衷)
1. **引擎在框架,不在你**。页面操作、接口调用、接口↔库对账、页面↔接口、造数→断言→diff→清理、出报告——全部由框架(`run_batch.py` / `core/*`)**确定性**完成。你只做"读散文→草拟规格→人审→触发执行→回写知识"。**绝不**自己临场点页面/发请求代替框架跑,那会丢掉确定性与多方校验。
2. **框架零业务,业务全落 workspace**。接口地址、库表、账号、模板、路由只写进 `workspace/`(已 gitignore)。不要把业务词写进 `core/`。
3. **写操作必须可清理**:任何造数规格都要带 `cleanup`(子表按父单号删 + 主表按标记删)和 `allowed_tables`;没清理不许跑写。
4. **人审门禁**:草拟出的规格先 `verify_status: draft`,把"调什么/填什么/断言什么/清理什么"亮给用户确认,确认后才改 `human_verified` 再执行。

## 步骤

### 1. 读用例
从 Excel 行或用户给的文本拿到:名称、前置、步骤、预期、所属模块。抓住**预期里可机器判定的点**(落库某字段=某值、状态流转到 X、接口 code=0、返回精度……)。

### 2. 查路由与自发现四来源(决定"调什么、填什么")
- 路由:`workspace/config/case_routes.yaml` 里该用例/功能的 `endpoint / table / template / db / session / approve`。没有就问用户补,或先 `python run_verify.py probe` 探一次。
- 四来源(有啥用啥,拼出"要填哪些字段、填什么合法值"):
  - 库约束/枚举/样例:`core.discovery.db_intel.table_constraints(db, table)` / `sample_values(...)`
  - 前端校验/控件:`core.discovery.fields.discover_fields(page)`(需登录态)
  - PRD/技术方案:`core.discovery.docs.DocIndex([...]).search([...])`
  - 已学知识:`core.discovery.knowledge.FieldIntel(feature)`(秒填 + 进化)
- 名称/标题类一律用唯一标记 `{{marker}}`(可识别、可清理)。
- **写接口 + 提交体模板不要手写**:对写页面 `run_verify probe --record` 录一次写操作,`prober.pick_write_call()` 自动挑出写调用,`write_stub_from_capture()` 产出 `endpoint`(method+path)+ 提交体模板;清理子表和标记字段由框架按库 schema/模板自动推导(route 只需给表名 + 预期状态)。

### 3. 草拟 ExecSpec(YAML,字段见 `core/spec.py`)
按用例类型拼:
- **查询类**(列表/检索/详情):`mode: reconcile`,`feature`+`db`+`request`(现调接口),对账自证一致,无需额外断言。
- **写入类**(新建/提交/暂存/状态流转):`mode: api`,
  - `request`:`endpoint` + `body`(模板去服务端字段、`{{marker}}` 注标题/幂等键、按**本例预期**设具体入参值,如 `quantity/unitPrice`);
  - `assertions.db`:把**预期**翻成断言——`where`(按标记定位,子表用父单号子查询)、`row_count`、`fields`(落库某列=预期值,体现"服务端重算/状态流转"等);
  - `approve`:若用例要走审批,带上(businessKey 可从响应或库取);
  - `cleanup` + `allowed_tables` + `verify_poll`(异步翻转等待)+ `diff_full_scan: false`(级联写入);
  - 预期被拒的守卫/校验:`assertions.response.rejected: true`;前置状态单:`prepare_state: <状态名>`(配 `state_recipes/<feature>.json`);异步事件:`assertions.events`。
- **UI 行为类**(字段联动/只读、页签计算、前端校验):`mode: ui` + `ui.page_model`(回放),断言用 `ui.field_asserts`(联动值/只读态)、`ui.value_asserts`(页签/按钮数↔库)、`ui.expect_validation`(前端校验报错)。
> **校验/拦截类先判层**:后端校验(接口会拒)→ API 层 `rejected:true`;前端校验(控件禁选/红字,后端信任不复查)→ **走 UI** 填非法值读报错 `expect_validation`。判错层会误报(如"过去日期"若是前端校验,API 提交会成功——TC20 实测如此)。拿不准查 PRD/技术文档或探一次。
把草拟结果写到 `workspace/specs_auto/<case_id>.yaml`,`verify_status: draft`。

### 4. 人审
把关键几行(调哪个接口 / 填了什么 / 断言什么 / 怎么清理)摘给用户确认。确认后把 `verify_status` 改 `human_verified`。

### 5. 执行(交框架,别自己跑)
```bash
python run_batch.py --specs workspace/specs_auto
```
框架会:发请求/开页面 → 多方校验(接口↔库、页面↔接口)→ diff 安全网 → 按标记清理 → 出 `workspace/runs/<run>/report.html` 富报告(做了什么/预期/实际/查的库表/SQL/截图/录像)。多次运行看 `workspace/runs/index.html` 总览(通过率趋势)。只读类可 `--workers N` 并发提速。

UI 控件定位失效时,`ui_actions.replay`/`ui_heal.resolve_input` 支持传入 `llm_resolver(label, candidates)`:确定性策略(form-item/label/placeholder/aria)全失败时,由你(会话 LLM)读候选控件+附近文字选一个 CSS 选择器兜底,命中记 `heal=llm` 回写知识待审。

### 6. 回写知识(自进化)
把本次确认好的字段/填法/枚举记进 `FieldIntel(feature)` 并 `save()`,下次同功能更快、更准。

## 批量
用户给一份 Excel 时:框架能确定性建模的(有路由+映射/模板的)直接
`python run_batch.py --excel <xlsx> --auto-model` 跑;其余"确定性建不了"的用例,逐条按上面步骤由你草拟补齐,落到 `workspace/specs_auto` 再执行。

## 产出给用户
报告路径 + 一句话结论(通过/失败几条、失败差在哪字段、残留是否清零)。不复述全过程。
