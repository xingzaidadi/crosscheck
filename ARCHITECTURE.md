# crosscheck 架构与移植说明

> 本文是"全貌 + 怎么移植 + 新手怎么用 + 工程演进路线"的归档。配合根 `README.md`(快速上手)阅读。

## 1. 它是什么

把**散文测试用例**自动变成**机器能执行、能判对错的多源校验**,一键批量回归。
核心本事是 **三源对账**:同一件事同时核 **页面显示 == 接口返回 == 数据库落库**,三边一致才算真过。
这是人工点点点给不了的——它能测"该拒的有没有拒""幂等有没有失效""库里落的值对不对"。

## 2. 执行流程(6 层管线)

```
①接入      ②自发现       ③就绪门禁     ④建模        ⑤执行            ⑥报告
bootstrap → preflight →  readiness →  spec/model → engine        → report
(登录/画像) (探库/接口/页) (能不能跑)   (散文→ExecSpec) (造数→动作→审批   (HTML+清单)
                                                    →三源校验→不变式
                                                    →哨兵→清理)
```

- **执行期不碰 LLM**:确定性回放,同一规格每次结果可比(防假通过)。
- **零业务门禁**:`tests/test_no_business_in_core.py` 扫 `core/`,出现任何业务词即失败——保证 core 可移植。

## 3. 输入 / 输出 / 过程展示

| 项 | 内容 | 位置 |
|---|---|---|
| **输入·用例** | 散文用例(中文表头自动认列) | `workspace/cases/*.xlsx`(也支持 csv/json) |
| **输入·画像** | base_url / 登录方式 / 用哪个库 | `workspace/profiles/<site>.yaml` |
| **输入·库** | 只读对账库 + 写库(造数/清理) | `workspace/config/db.yaml` |
| **输入·凭据** | 账密 + `act_as`(impersonate) | `workspace/config/credentials.yaml` |
| **输入·路由** | 用例→接口+断言(建模核心配置) | `workspace/config/case_routes.yaml` |
| **输入·报文** | 真实请求模板 / 动作桩 | `workspace/captures/`、`knowledge_base/action_stubs/` |
| **输入·(规划)源码** | 读接口契约+校验规则,替代逆向 | 另给 git 仓库 |
| **输出·单次** | report.html / summary.json / 逐条证据(截图/报文/SQL) | `workspace/runs/<运行ID>/` |
| **输出·清单** | 终态清单 / 缺陷清单 / 环境需求清单 / 就绪图 | `workspace/findings/`、`workspace/readiness.yaml` |
| **过程展示** | 控制台 `[i/N] TCxx …` → `[通过/失败/跳过]+原因`,末尾小结 + 报告路径;UI 类录屏录图 | 控制台 + runs 目录 |

## 4. 基础建设 vs 业务(移植指南)

**移植给别人 = 拿"基建",不拿"业务"。**

### 拿走(通用框架,零业务)
- **`core/`** — 全部机制:`engine`(执行)、`spec`/`modeler`(建模)、`verifier`/`reconciler`/`snapshot`(校验)、`invariants`/`roundtrip`(不变式)、`cleaner`(清理)、`prober`/`actionmap`(录放)、`readiness`(就绪门禁)、`registry`(插件注册表)、`disposition`(用例去向)、`connectors`(适配器工厂)、`login`/`profile`/`workspace`/`case_source`、`discovery/`(探库/接口/页面)、`envneeds`(环境需求)。
- **`adapters/`**(api / playwright)、**`db/`**(连接)。
- **根入口**:`run_crosscheck.py`(一键)、`run_batch` / `run_verify` / `run_preflight` / `run_bootstrap` / `run_record`。
- **`tests/` + `run_tests.py`**:自测 + 零业务门禁(可移植性守门员)。
- **空 workspace 模板**:`config/*.yaml` 模板 + 目录骨架。

### 留下(本业务,换系统即换)
- `workspace/` 全部内容:本系统的 cases / profiles / credentials / db.yaml / case_routes / captures,以及 142 条语料。
- 迭代残留的 `workspace/specs_*`(实验目录,移植前应清,见 §6)。

一句话:**core + adapters + db + 入口 + tests = 基建;workspace = 用户自己的料。**

## 5. 新手怎么用

**一句话介绍**:"你把用例用大白话写在 Excel 里,它自动去点页面、调接口、查库,**三边核对一致才算过**,一键出报告。不用手工点,也不用写测试代码。"

**五步**:
1. 填 3 个配置:`profiles/<site>.yaml`、`config/db.yaml`、`config/credentials.yaml`。
2. 登录一次:`python run_verify.py login --profile <site>`(弹浏览器登一次,存 cookie)。
3. 用例 Excel 丢进 `workspace/cases/`。
4. 一键:`python run_crosscheck.py --workspace workspace`。
5. 看 `workspace/runs/最新/report.html`。

**诚实边界**:接口/UI 类用例目前还需配一点"路由"才能自动跑,不是纯傻瓜;这正是"源码输入"要消除的瓶颈(见 §6)。

## 6. 工程演进路线(借鉴 dsh-record-and-replay)

对比 [dsh-record-and-replay](https://github.com/kakaCat/dsh-record-and-replay)(Agent 语义动作录放回归,产品化程度高):

**我们领先**:三源对账(页面==接口==库)、散文直接建模、负例/幂等/库落值校验、造数清理哨兵、core 零业务可移植。
**我们落后、要补**:
1. **捕获人机工学**:学它"旁路实时录语义动作",替代现在"我写脚本逆向"(今天逆向还误关过单)。
2. **工程化**:它有面板 UI / 实时 HUD / CLI 测试套件 / CI / 隐私掩码;我们是脚本堆 + 几十个乱 `specs_*`,待清理打包。
3. **语义回放自愈**做成一等引擎(现在只临时加了点击自愈)。
4. **Skill 知识库 + 评审流**规范化。

**最高优先级(治本)·已落地 v1**:**源码→接口契约建模**。现在 142 里 108 条卡在"没建模"(靠逆向,又慢又脆)。读后端源码把建模从"逆向猜"变"读契约"。

已实现 `workspace/scripts/extract_contracts.py`(Spring/Java 通用):扫 `*Controller*.java` 得端点 → 顺 `@RequestBody` 找请求 DTO → 读 DTO 字段 + 校验注解(`@NotBlank/@NotNull/@Size/@Max`…),产出机器可读契约目录 `workspace/knowledge_base/contracts/<site>.json`。
- 用法:`python -I workspace/scripts/extract_contracts.py <源码根> <服务上下文如 demand> --site <站点>`。
- 已对 `ebuy-demand`(分支 `feature/dev-xuzhijun-gloabl-logistics`)提取 36 个端点,拿到 item/close、template/data/save、close/recall/discard/return/transfer 等**此前靠 UI/抓包逆向不到的**精确契约。
- 价值验证:TC101 明细关闭直接用契约 `DemandItemCloseRequest{demandRequestCode,itemId,version}` 建模一次跑通(未碰 UI)。
- 附带洞察:`SaveDemandRequest` 70 字段/0 必填、无 `@Size/@Past` → 超长描述/过去日期在 DTO 层无校验,TC138/TC20 的"该拒"要么是真缺陷、要么校验在 service/domain 层(可继续顺源码核实)。

> 仓库地图(group `mit/finance/ma/ip`):`ebuy-demand`(需求,本测试对象)、`ebuy-supplier`(供应商)、`ebuy-sourcing`(寻源)、`ebuy-contract`(合同)、`ebuy-foundation`、`ebuy-front-web`(前端,UI 类用例可据此读页面结构替代探测)、`ebuy-ddd-framework`。
