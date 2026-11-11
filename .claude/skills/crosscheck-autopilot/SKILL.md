---
name: crosscheck-autopilot
description: 自主把一批用例推到底——卡住先查库/试页面/写原语自救,只有真外部或规则未定义才问人,全程诚实分诊、绝不造假绿。触发场景:用户说"继续推用例/这批自测/把剩下的跑完/逐条建场景数据/别停下来问"。不触发:只问框架怎么用、只改 core 框架码、与用例执行无关的闲聊。
---

# crosscheck-autopilot:自主建用例 · 诚实分诊 · 不糊弄

你在 crosscheck 框架里**自主**把给定的一批用例推到底。目的只有一个:**解放人**——能自己查、自己试、自己写代码搞定的,绝不回头要人输入;真搞不定的,**诚实分诊**,绝不把结论凑绿。

配套:建模前端见 `crosscheck` skill;本 skill 管"拿到一批后怎么自主跑完 + 卡住怎么办 + 怎么收尾不骗人"。

## 铁律(违背了就是白干)

1. **自救优先,别把人拉进执行回路。** 缺东西时按序自救:① 能查库就查库 → ② 能在页面/UI 试的就去试(上传、按钮、字段联动)→ ③ 缺能力就写原语/脚本。**只有**这三样都不行——产品规则本身未定义、外部系统且库里无镜像、环境未配的枚举/场景——才问用户,且**一次问清**。报"需用户给"之前,先 SELECT 查一遍、或在页面走一遍。(教训:受理人其实查 `demand_item_assignment_record`、汇率/BR 其实都在库里,别再张口要账号/样本。)

2. **别糊弄(最高优先)。** 只报**真跑出的真定论**。建不出就**诚实分诊**,绝不:
   - DB 直插/造态把"被测的结论"塞进去当绿(如直插 EXECUTED/FINISHED 冒充完成事件);
   - 把工具/环境/历史数据问题当成产品缺陷报(先说"疑似/待开发确认口径",别拍 bug);
   - 用页面级或部分断言冒充逐行规则验证(覆盖不到的诚实标"未覆盖")。

3. **批量一口气跑完,不逐条停下问确认。** 给定一批就自己做完三源研究→建能建的→`--only A,B,C` 批量跑→最后一次性报。中途别问"这样行不行/要不要继续"。

4. **框架零业务,业务落 workspace;新能力沉淀成原语。** 别把业务词写进 `core/`;可复用机制做成通用原语(见下),不硬编码单条用例。

## 建用例决策树(按"被测的是什么"选路子)

- **计算结果 / 带出值**(汇率换算、本外币金额、BR 带出财务字段):**对账式**——核对**既有真实单**,别造单。草稿阶段不触发计算、模板默认是占位值(币种 ADP/金额 0),造单路线不稳;用户口径就是"核对就 `SELECT ... WHERE demand_request_code=...`"。用 `mode: write` + 显式 `request: GET detail/<真实单>` + `extra_db_asserts` 核对库值(算术不变量、带出字段落库)。只读、不清理。
- **办理人 / 角色**(受理人、审批人):按单从库/接口查**真实办理人**再 `login_as` act-as,**不要账号**。受理人→`demand_item_assignment_record.assignee_user_id`(assign_status=SUCCESS);审批人→`approval-records` 取 taskId+待审批人。口径见 `workspace/knowledge_base/business_facts/actor_resolution.json`。
- **浏览器 / 外部系统驱动**(引擎 API 复刻不出的,如 BPM 驳回):`mode: script` + `script: <路径>`,脚本随 `run_batch` 跑、自动解析 VERDICT。
- **异步"完成态"**(明细 FINISHED/EXECUTED、头单完成联动——下游 MQ/事件驱动):**诚实判 NEEDS_TRIGGER**。需求服务只有事件消费口(`/x5/bpm/processFinish`),没有节点完成接口;DB 直插 = 伪造被测结论 = 假绿。给一个真实"执行完成"事件触发入口才能 faithful 做。
- **UI 可试的**(附件上传、按钮可见/隐藏、字段隐藏联动):**先走页面三层**(`mode: ui` / page_probe / uicapture),不要依赖用户给"接口口径";真走不通再说。
- **写入 / 状态流转**(受理退回、修改暂存/提交、节点生成):`mode: write`,`request`/`endpoint` + `assert_status`/`extra_db_asserts`;`data_prep` 造前置(draft→save→submit→BPM approve→`db_wait` 到目标态)。

## 已沉淀原语(路由 `workspace/config/case_routes.yaml` 里直接用)

- `data_prep` 复合步:`db_wait`(轮询状态翻转)/ `db_capture`(查库抓值进 vars,供 `{{var}}`)/ `db_exec`(造夹具)/ `http`(造数,可带独立 `session`/`base_url`)。
- `login_as: {site, act_as: "{{抓到的办理人}}", session_var}`:headless 换身份登录 + 重绑写动作会话。act_as 要**登录名**(assignee_user_id),不是工号。
- `capture_poll`:响应值轮询抓取。
- `mode: script` + `script:`:浏览器/外部驱动用例随批量跑、自动解析 VERDICT。
- `extra_db_asserts`:`{table, where, row_count / row_count_min, fields}`;算术不变量用 where 里 `ABS(a-b*c)>容差` + `row_count: 0`;唯一性用 dup-finder 子查询。
- `assert_status: {column, value}` / `assert_where` / `cleanup_children` / `verify_poll`。

## 自查数据落点(查了就用,别问用户)

见 `workspace/knowledge_base/business_facts/`:`actor_resolution.json`(办理人)、`self_serve_checklist.json`(汇率在 `demand_request_item.to_cny/to_usd_exchange_rate`、BR 在 `budget_apply_no/cost_center_code/wbs_code`、以及"先查库再试页面"的通则)。接新业务往这里加。

## 流程

1. 拉清单:`workspace/findings/执行清单_manifest.md` 看每条终态/归属;挑这批要推的。
2. 逐条按决策树定路子;需要的真实单号/办理人/枚举**先查库**(`db.client` 只读连 + `config.db_params`),查到就用。
3. 建能建的路由(改自己的区块前先 Read,避免和并行会话互相覆盖;flow 映射里含 `{{var}}` 的值一律加引号)。
4. 一个批次跑完:`python run_batch.py --excel <xlsx> --auto-model --only A,B,C --ensure-login --no-cleanup`。
5. 建不出的**当场诚实分诊**:改 `workspace/config/env_needs_rules.yaml` 的 need 文案(写明"给什么能解")或 `run_manifest.py` 的 classify;产品口径类标 BLOCKED。

## 收尾自检(报之前过一遍)

- 每条都有**真 verdict**?PASS 是真三源通过、不是造态?FAIL 是真不一致?
- 有 fidelity/audit 的,分数达标、审计没缺"UI 驱动"?不达标就自己补,别报假绿。
- 疑似数据/口径问题标了"待开发确认",没当缺陷拍?
- 诚实边界写清了(哪部分覆盖、哪部分未覆盖)?
- `python tests/test_no_business_in_core.py` 零业务门禁绿、离线测试绿?

## 产出给用户

一句话结论:通过几条 / 失败几条(差在哪)/ 诚实阻塞几条(缺什么能解)。给报告路径,不复述全过程。保留造数作证据(`--no-cleanup`),不删。
