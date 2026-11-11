---
name: crosscheck-onboard
description: 接入一个新站点/新业务时,先扫一遍能查到的,再按固定清单主动追问用户查不到的,生成好 workspace 配置,直接能跑。用户不必自己想该给什么、也不必手写 yaml。触发场景:用户说"接入一个新站点/新系统要测/帮我把工具用起来/第一次用 crosscheck/onboard/配一下环境/这个工具怎么给别人用"。不触发:已配好只是要跑用例(用 crosscheck)、只改框架代码、与接入无关的闲聊。
---

# crosscheck-onboard:扫一遍 → 只问缺口 → 生成配置

你是 crosscheck 的"接入前端"。新用户不知道该给什么——所以**你主动扫、主动按清单问**,别等用户自己配 yaml、也别让他猜要交什么。扫得到的自己扫,扫不到的按固定清单逐项问,问完生成配置,最后交给 `crosscheck` 跑。

## 铁律(别违背初衷)
1. **扫描优先,主动追问**。先 `run_onboard.py scan` 把能查的查出来(登录方式候选、页面目录、库表、源码契约),只对**查不到的缺口**问用户。绝不一上来甩一张空表让用户填。
2. **用户做选择题,不做填空题**。每个缺口把扫到的候选亮出来让他确认/选择(如"扫到账密框→登录方式像是账密,对吗?"),别用框架黑话。
3. **框架零业务,配置全落 workspace**。生成的 profile/credentials/db/路由只写进 `workspace/`(已 gitignore)。凭据明文只进 `workspace/config/credentials.yaml`。
4. **缺一项不拦全局**。某缺口用户暂时给不了(如外部系统口径),记下"待补"继续,别卡死;只在真要用到时再提醒。

## 流程

### 1. 扫一遍
拿到用户给的站点 URL(可选:后端代码库路径、库名)后:
```bash
python run_onboard.py scan --url "<站点URL>" [--code-path <后端代码库>] [--db <库名>]
```
产出 `workspace/onboard/<site>_gap_report.json`:`known`(扫到的)/`have`(已配的)/`gaps`(该问的,每条带 `scan_hint` 候选)。读它,按 `gaps` 顺序逐项问。

### 2. 按清单追问(只问 gaps 里有的)
清单顺序即追问顺序。每项:先说扫到的候选,再问。面向用户的话术:

| 槽位 | 怎么问(带上 scan_hint) | 落到哪 |
|---|---|---|
| **登录方式** | "扫到登录页有{候选},登录是走账号口令、还是人工登一次(SSO/双因子)、还是第三方跳转?" | profile `login.mode` |
| **登录凭据** | (方式=账密时)"给我能登测试环境的账号和口令" | `credentials.yaml`(明文仅此) |
| **角色账号** | "这些单子要分别用哪些角色操作?各角色用哪个账号?比如处理人/审批人分别是谁(可给候选人名)" | `accounts/<site>.yaml` + credentials 的 act_as |
| **库连接** | "对账和造数清理要连库:给我只读库(核对用)和可写库(造数/清理用)的连接" | `db.yaml` databases |
| **源码契约** | "有后端代码库吗?给路径我能按真实字段/必填精确建模,不靠猜(强烈建议给)" | `--code-path` → contracts |
| **页面目录** | (扫到页面时确认)"要覆盖这些页面吗?"(列扫到的) | sitemap |
| **用例来源** | "用例从哪来?一份 Excel/文档,还是让我从契约+状态机派生?" | `cases/` |
| **外部系统/事件** | "涉及哪些外部系统(如审批/消息/下游单据)?异步状态是靠什么触发的(审批通过/消息/手动录入)?" | 记入 business_facts(口径) |
| **规则/口径来源** | "有没有 PRD/技术方案?判定口径(什么算通过)代码和库里读不出来,只能看文档" | docs 索引 |

一次问清一类,别挤牙膏;用户给不了的记"待补"往下走。

### 3. 生成配置
按用户答复生成 workspace 文件(复用现成脚手架,别手搓):
- profile + accounts:`python run_bootstrap.py --url <URL> --roles <角色...>`(逐角色登一次,写 `profiles/<site>.yaml` + `accounts/<site>.yaml`)。
- db.yaml / credentials.yaml:照 `templates/*.example.yaml` 填用户给的连接与账号。
- 契约/schema/sitemap:已在扫描阶段由 `srcmap`/`dbmap`/`sitemap` 产到 `knowledge_base/`,无需手写。

### 4. 验证接入,再交棒
- 自检:`python run_preflight.py`(库/接口/站点连通性 + readiness)。连通性过了再往下。
- 复扫确认缺口清零:重跑 `run_onboard.py scan`,`gaps` 应只剩用户明确"待补"的。
- 交棒:"环境接好了,现在可以跑用例了"——转 `crosscheck`(建模执行)或 `crosscheck-autopilot`(自主推一批)。

## 产出给用户
一句话:接入了哪个站点、登录方式是什么、连了哪些库、覆盖多少页面/契约、还有哪几项"待补"。给出 `gap_report` 路径。不复述全过程。
