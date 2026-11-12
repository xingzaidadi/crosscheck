# crosscheck

自动化驱动的跨层一致性验证框架:交叉核对 UI → 接口 → 数据库三层是否对得上。人只给一个页面
URL,工具自己驱动真实浏览器(登录、声明式操作、录像/截图)跑一遍流程,抓下它触发的接口流量,
自动建模成「接口参数 → SQL」映射(人审一次),再连库把接口返回和数据库对账,证明列表/检索结果
是否可信。换一套页面、换一套库 = 新写一个 profile,内核一行不改。

## 快速上手(新系统三步)

```bash
python run_bootstrap.py https://你的系统/任意页面   # ① 浏览器登一次,自动生成 profile(不用写 yaml)
python run_preflight.py <site>                      # ② 自发现环境:库结构/接口目录/站点,出就绪图
python run_crosscheck.py --workspace workspace      # ③ 一键跑完:自动建模+UI+自定义检查→清单+报告
```

- 第 ③ 步一条命令覆盖 接口 + UI + 自定义不变式(放 `workspace/checks/*.py`),出 HTML 报告 + 142 终态清单。
- 每次 Excel 跑批前先生成套件指纹与分类覆盖计划:`suite_plan.md/json` 会列出测试意图、要求的 UI/API/DB 层、已具备层和缺口；case_id 被新套件复用时，旧路由/规格不会直接覆盖。
- 自测整套框架:`python run_tests.py`(含零业务门禁)。

## 这是什么

不是"每次让 AI 看页面猜一遍"的工具,而是:

> **知识前置、执行只回放、状态 diff、数据隔离。**

介质(页面/接口/消息/任务)是可替换的适配器;知识库 + 断言 + diff + 清理是通用内核。
框架本身零业务:你的站点配置、库连接、知识库、抓取样本都放在一个自管的 **workspace** 目录里,
不进框架仓库。

## 目录结构

```
框架仓库(通用,可发布)                 workspace/(你自管,不提交)
├── core/          通用内核             ├── profiles/        站点 *.yaml
│   ├── workspace.py  路径解析器        ├── config/          db.yaml / credentials.yaml
│   ├── prober.py     抓包探针          ├── knowledge_base/  query_mapping / page_model / ...
│   ├── mapping_builder.py 自动建模草稿  ├── actions/         声明式检索动作
│   ├── query_mapper.py 参数→SQL        ├── cases/           结构化用例
│   ├── reconciler.py 连库对账          ├── captures/        抓取样本
│   ├── report.py / reporter.py 报告    ├── artifacts/       录像/截图/报告产出
│   └── executor/verifier/cleaner/...   └── .auth/           登录态
├── adapters/      可插拔适配器(api / playwright)
├── db/            DB 访问(只读优先)
├── templates/     无业务样例(profile / db / credentials)
├── scripts/init_workspace.py  一条命令建 workspace 骨架
├── tests/         中性样例域的回归测试
├── run.py / run_record.py / run_verify.py  入口
└── .gitignore     忽略 /workspace/
```

## workspace:业务数据放哪

框架通过路径解析器 `core/workspace.py` 找业务数据,优先级(高→低):

1. 入口脚本的 `--workspace <dir>` 参数
2. `VTA_WORKSPACE` 环境变量
3. `./workspace`(仓库根下存在该目录则用)
4. 仓库根(非破坏性回退:没建 workspace 时老布局继续能跑)

## 设计要点

1. **回放优先**:日常按知识库选择器回放,选择器失效才 AI 自愈。
2. **API-first**:能走接口校验的别开浏览器,只有测 UI 逻辑才用 Playwright。
3. **Playwright 为主,CDP 为逃生舱**:99% 用高层 API,需要专有能力再 drop 到 CDP。
4. **三重校验**:页面预期 + DB 精确断言 + diff 安全网(实际动的表 ⊆ allowed_tables)。
5. **数据隔离**:`AUTOTEST_` 标记 + 哨兵快照 + 失败也清 + 清理失败兜底。
6. **初期强制串行**:哨兵快照/diff 前提是测试库安静,并发是后期的事。

## 核心能力(有回归测试覆盖)

- **抓包 → 自动建模**:给一个 URL,探针抓出检索接口的请求体+返回,`build_mapping_draft`
  自动推出「参数→列」映射草稿、识别分组字段与抽样比对列,停下等人审。
- **参数 → SQL**:`QueryMapper` 把接口参数确定性翻成 WHERE(枚举翻译、`IN`、`LIKE`、
  绑定参数防注入),并跳过"不筛选"哨兵值(如 `-1` / 空数组)。
- **连库对账**:`Reconciler` 比分组计数、总数(`COUNT(DISTINCT 主键)`)和字段抽样。
- **`joins` + `table_alias`**:接口参数落在关联表而非主表时(需 join 才能表达的隐含过滤),
  数量核对自动走 `COUNT(DISTINCT 主键)` 去重。
- **`response_field_map`**:接口 camelCase 字段名 ↔ 库 snake 列名的翻译,是字段抽样比对的前提。

## 通用化:换一套页面 / 一套库怎么用

站点身份(登录方式 / URL / 库绑定 / 抓取默认值)不写死在代码里,放 `<workspace>/profiles/<站点>.yaml`。
**上线一个新站点 = 填一个 profile + 在 `db.yaml` 加一条库 +(仅 B 模式)在 `credentials.yaml`
加账号,内核(抓包/建模/对账)一行不改。** 模板见 `templates/profile.example.yaml`。

登录两种模式(由 profile 的 `login.mode` 决定),登录态按站点存 `<workspace>/.auth/<站点>.json`,失效才重登:

- **A `manual`(推荐默认)**:开浏览器人工登一次,能过 2FA/验证码/SSO/两段式。
- **B `credential`**:声明式 `login.steps` 自动填账密、点登录;只适合简单账密页。
  账号在 `credentials.yaml` 的 `sites.<站点>` 下,profile 只按 `value_from` 引字段名。

## 跑

```bash
# Python 3.10+。建议在虚拟环境中安装。
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
# 需要完全复现已验证版本时,改用: python -m pip install -r requirements.lock
python -m playwright install chromium
python scripts/preflight_install.py

# 1) 建一个 workspace 骨架(自管业务目录)
python scripts/init_workspace.py ./workspace

# 2) 填连接与站点(都在 workspace 里,不进框架仓库)
cp workspace/config/db.example.yaml workspace/config/db.yaml                 # 填真实连接
cp workspace/config/credentials.example.yaml workspace/config/credentials.yaml  # 仅 B 模式需要
#    按 workspace/profiles/_example.yaml 写 workspace/profiles/<你的站点>.yaml
```

列表/检索校验流程(人只给页面 URL;probe 前会自动确保登录态):

```bash
python run_verify.py login --profile <你的站点>       # 建立/刷新登录态(A 模式开浏览器登一次)
python run_verify.py probe --profile <你的站点>       # 自动登录态→抓接口→建模,产出映射草稿待人审
python run_verify.py reconcile --profile <你的站点>   # 用审过的映射连库对账出报告
```

> 把 `./workspace` 命名成别的位置时,给每条命令加 `--workspace <dir>`,或设 `VTA_WORKSPACE`。

## 安全边界

- 只连接隔离测试环境。查询使用只读账号;造数/清理使用独立、最小权限的写账号,不要连接生产库。
- `cleanup` 是删除操作的显式白名单,且写入规格必须配置 `allowed_tables` 作为变更安全网;所有表名和列名都会校验为 SQL 标识符,不接受 SQL 片段。
- `credentials.yaml` 和 `.auth/` 含明文口令或登录态,只能保存在自管 workspace,不得压缩、提交或转发。
- workspace 中的 Python 文件拥有当前用户权限,不是安全沙箱。默认不执行;只有确认来源可信时才加 `--allow-workspace-scripts`。
- 对外分发不要手工压缩仓库目录。执行 `python scripts/build_release.py`,它只打包 Git 跟踪文件并拒绝敏感路径。

## 测试

```bash
python run_tests.py                    # 完整离线回归(交付前必跑)
python tests/test_prober_capture.py     # 抓包 → 自动建模
python tests/test_reconcile.py          # 参数→SQL / 枚举翻译 / join / 字段映射 / 一致&不一致
python tests/test_sentinel_total.py     # 哨兵值跳过 + 总数核对
python tests/test_pipeline.py           # probe → 人审 → reconcile 整条命令链
python tests/test_profile_login.py      # profile 加载 + 声明式登录步骤
python tests/test_record_report.py      # 录像/截图/接口/报告 四件套
```

测试全程用一个中性样例域(表 `items`、接口 `/api/items/search`、feature `列表检索`),
本地起网页 + sqlite,不碰任何真实环境。

## 发布

项目采用 MIT License。交付前执行:

```bash
python run_tests.py
python scripts/preflight_install.py
python scripts/build_release.py
```

发布包输出到 `dist/crosscheck-source.zip`,不会包含本机的 `workspace/`、凭据、登录态、抓包或报告。

## Agent / Skill 使用

仓库内提供 `.agents/skills/crosscheck/SKILL.md`。支持 repo-local Skill 的 Agent 打开本项目后，可按该 Skill 编排 CLI。

Skill 的第一阶段固定为**自动收集信息**，随后以 pipeline 形式连续执行：读取现有 profile、workspace、用例和 readiness，自动完成安装预检、环境检查、登录态检查、dry-run 和小批试跑。pilot 通过且安全门禁正常后，会直接批量执行所有当前 READY 用例，不再询问是否继续；draft、blocked 和覆盖缺口项进入报告。只有无法确认非生产环境、需要人工登录、写入权限/清理范围或脚本信任边界时才提问。它不会要求用户在对话中粘贴密码、Token 或 Cookie。

推荐让用户用自然语言提出任务，例如“帮我接入这个测试系统”或“执行这批 Excel 用例并分析报告”；Agent 负责收集缺失信息和选择命令，crosscheck CLI 负责确定性执行与判定。

## 标准套件 DSL

复杂业务建议先将散文 Excel 导入套件级隔离目录：

```powershell
python scripts/import_suite.py cases.xlsx --workspace workspace --suite-id my-system-feature-v1 --profile my-system
python scripts/score_suite.py workspace/suites/my-system-feature-v1
python run_suite.py --suite workspace/suites/my-system-feature-v1 --workspace workspace --plan-only
python run_suite.py --suite workspace/suites/my-system-feature-v1 --workspace workspace --ensure-login
```

目录中的 `suite.yaml` 描述环境和执行策略，`cases/*.yaml` 使用 fixture → action → assertion → cleanup 格式。`case_id` 为套件级全局唯一值，原 Excel 的 `TC01` 只保存在 `source.case_key`，从根源上避免旧套件同编号规格串入。模板见 `templates/suite.example.yaml` 和 `templates/case.example.yaml`。

case-gen YAML 使用 `python scripts/import_casegen.py ...` 导入。正式执行由 `run_suite.py` 从 canonical case 编译执行计划；共享 `workspace/specs_verified` 和 `run_batch.py --excel` 仅保留为迁移兼容路径。

完整能力验收标准见 `docs/GENERAL_TOOL_ACCEPTANCE.md`；优化设计与历史错位见 `docs/OPTIMIZATION_ROADMAP.md`。
