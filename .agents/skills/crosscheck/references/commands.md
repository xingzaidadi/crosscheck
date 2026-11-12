# 命令选择

所有命令都从 crosscheck 项目根目录执行。路径含空格时加引号。

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock
python -m playwright install chromium
python scripts/preflight_install.py
```

## 初始化

```powershell
python scripts/init_workspace.py <workspace>
```

## 导入并评分标准套件

```powershell
python scripts/import_suite.py <cases.xlsx> --workspace <workspace> --suite-id <全局唯一套件ID> --profile <site>
python scripts/import_casegen.py <case-gen.yaml> --workspace <workspace> --suite-id <全局唯一套件ID>
python scripts/score_suite.py <workspace>/suites/<suite-id>
python run_suite.py --suite <workspace>/suites/<suite-id> --workspace <workspace> --plan-only
python run_suite.py --suite <workspace>/suites/<suite-id> --workspace <workspace> --ensure-login
```

导入后每条用例都有全局唯一 `case_id`、来源行和要求层。补齐 fixtures/actions/assertions/cleanup 后，把 `status` 改为 `ready`，再把编译规格放入该套件自己的 `specs/`。
正式路径不再手工维护 `specs/`；`run_suite.py` 从 canonical case 编译不可变计划。`approval.content_hash` 必须匹配当前内容，修改用例后审批自动失效。

## 接入扫描

先用 `python run_onboard.py scan --help` 查看当前参数。适合已有部分 URL、数据库或源码，但不知道缺什么的场景。

## 环境预检

```powershell
python run_preflight.py <site> --workspace <workspace>
```

可通过 `--only db,api,site` 缩小范围。

## 登录、抓包和对账

```powershell
python run_verify.py login --profile <site> --workspace <workspace>
python run_verify.py probe --profile <site> --workspace <workspace>
python run_verify.py reconcile --profile <site> --workspace <workspace>
```

执行前用对应的 `--help` 确认子命令参数。

## 跑批

先生成天然分类和 UI/API/DB 覆盖计划：

```powershell
python run_batch.py --workspace <workspace> --excel <cases.xlsx> --auto-model --plan-only
```

查看运行目录中的 `suite_plan.md`；其中会列出套件指纹、测试意图、每条用例要求层、已具备层和缺口。

先做只读草拟：

```powershell
python run_batch.py --workspace <workspace> --excel <cases.xlsx> --auto-model --dry-run
```

先跑少量：

```powershell
python run_batch.py --workspace <workspace> --excel <cases.xlsx> --auto-model --limit 3 --ensure-login
```

定点复跑：

```powershell
python run_batch.py --workspace <workspace> --specs <spec-dir> --only TC01,TC02
```

只有已确认可信 workspace 才能附加：

```text
--allow-workspace-scripts
```

## 一键编排

预检、小批执行和清理均正常后，Agent 应自动使用，不再询问是否继续：

```powershell
python run_crosscheck.py --workspace <workspace>
```

## Pipeline 推荐顺序

Agent 默认按下面顺序自动执行，不在命令之间询问：

```powershell
python scripts/preflight_install.py
python run_preflight.py <site> --workspace <workspace>
python run_verify.py login --profile <site> --workspace <workspace>
python run_batch.py --workspace <workspace> --excel <cases.xlsx> --auto-model --dry-run --limit 3
python run_batch.py --workspace <workspace> --excel <cases.xlsx> --auto-model --limit 3 --ensure-login
```

如果 pilot 通过且环境/清理安全，自动执行 `run_crosscheck.py` 或等价的 READY 批次。只有用户明确要求“仅试跑”或指定 `--limit/--only` 时才停止；不得在 pilot 通过后询问是否继续批量执行。

## 框架验证与发布

```powershell
python run_tests.py
python scripts/build_release.py
```

不要通过 shell 拼接用户输入。调用命令时使用参数数组或安全引用路径。
