# api-db-reconcile

抓包驱动的「接口 ⇄ 数据库」一致性验证框架。人只给一个页面 URL,工具自己登录、抓检索接口、
自动建模成「接口参数 → SQL」映射(人审一次),然后连库把接口返回和数据库对账,证明列表/检索
结果是否可信。换一套页面、换一套库 = 新写一个 profile,内核一行不改。

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
├── run.py / run_record.py / run_p0.py  入口
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
pip install -r requirements.txt

# 1) 建一个 workspace 骨架(自管业务目录)
python scripts/init_workspace.py ./workspace

# 2) 填连接与站点(都在 workspace 里,不进框架仓库)
cp workspace/config/db.example.yaml workspace/config/db.yaml                 # 填真实连接
cp workspace/config/credentials.example.yaml workspace/config/credentials.yaml  # 仅 B 模式需要
#    按 workspace/profiles/_example.yaml 写 workspace/profiles/<你的站点>.yaml
```

查询类闭环(人只给页面 URL;probe 前会自动确保登录态):

```bash
python run_p0.py login --profile <你的站点>       # 建立/刷新登录态(A 模式开浏览器登一次)
python run_p0.py probe --profile <你的站点>       # 自动登录态→抓接口→建模,产出映射草稿待人审
python run_p0.py reconcile --profile <你的站点>   # 用审过的映射连库对账出报告
```

> 把 `./workspace` 命名成别的位置时,给每条命令加 `--workspace <dir>`,或设 `VTA_WORKSPACE`。

## 测试

```bash
python tests/test_prober_capture.py     # 抓包 → 自动建模
python tests/test_p0_reconcile.py       # 参数→SQL / 枚举翻译 / join / 字段映射 / 一致&不一致
python tests/test_sentinel_total.py     # 哨兵值跳过 + 总数核对
python tests/test_p0_pipeline.py        # probe → 人审 → reconcile 整条命令链
python tests/test_profile_login.py      # profile 加载 + 声明式登录步骤
python tests/test_record_report.py      # 录像/截图/接口/报告 四件套
```

测试全程用一个中性样例域(表 `items`、接口 `/api/items/search`、feature `列表检索`),
本地起网页 + sqlite,不碰任何真实环境。
