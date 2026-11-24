# 三段式流水线(用例转操作 · UI 操作 · 操作后验证)

> 定位:把一条大流程拆成三段**独立流水线**,每段产出一个**带契约的制品**,每段配一个
> **确定性校验门禁(checkpoint)**;由一个总控 Orchestrator 调度三个**写作用域隔离**的子 Agent。
> 核心价值不是"多 agent",而是**每段产物白盒可校验 + 只重跑出问题的那一段**。

## 为什么这么设计

传统一体化 agent 的痛点:转出来的操作文档对不对、验证逻辑符不符合预期,对你是黑盒;
让 agent 修一处,它可能把整条流程重写,对的也改错。三段式把它拆开:

- 每段产物有 schema + 契约校验 → **黑盒变白盒**,执行前就能按条判对错。
- 子 Agent 写作用域隔离 → **某段打回只重跑该段,上游产物只读不动**,杜绝"改一处全流程重写"。
- 总控只派段/判过闸/落盘/复用 → **不改判定规则**(判定契约在代码里,业务语义正确性仍走人审闸)。

## 三段与检查点

| 段 | 产物 | 契约(checkpoint) | 核心代码 |
|---|---|---|---|
| ① 用例转操作 | `exec_spec` | `validate_spec`:case_id、mode 合法、`verify_status=human_verified`、有可判定依据、无 `needs_review` | `core/modeler.py`、`core/spec.py` |
| ② UI 操作 | `actions` | `validate_actions`:非安全阻断、步骤可回溯到 spec(`from_spec`)、证据非空 | `core/ui_agent/runtime.py` |
| ③ 操作后验证 | `evidence` | `validate_evidence`:verdict 有值、三源(ui/api/db)声明齐且≥2 源、证据 `sha256` 齐、reconcile 有结论 | `core/verifier.py`、`core/reconciler.py` |

执行期零 LLM、确定性回放;契约只做结构/完整性判定,**不判业务语义**(那是人审 `human_verified` 的职责,刻意为之)。

## 模块一览(通用、零业务,可移植)

| 文件 | 职责 |
|---|---|
| `core/stage_contracts.py` | 三段产物 schema + `validate_*()` 契约 + 产物哈希(纯函数) |
| `core/stage_runner.py` | 子 Agent 协议 + 写作用域门禁(`enforce_write_scope`)+ `run_stage` |
| `core/orchestrator.py` | 单条用例三段调度:per-stage checkpoint、有界重试、过闸续跑、上游变即作废下游 |
| `core/stage_adapters.py` | 真实适配器:`ExecSpec/AgentRuntimeResult/ReconcileResult` → 三段契约产物 |
| `core/three_stage_wiring.py` | 装配闭包:modeler / UI runner(Playwright 惰性)/ 只读 DB 工厂 |
| `core/stage_batch.py` | 批量入口:多用例 + 复用 `circuit_breaker` 熔断转人工 |
| `core/stage_report.py` | 汇总 run-dir → `report.html`(含 UI 证据可点击缩略图)+ `report.json` |
| `run_three_stage.py` | 命令行入口 |

## 命令行用法

```powershell
# 离线:只跑第一段(建模 + CP-1),不起浏览器/不连库,快速看"用例转操作"产物对不对
python run_three_stage.py --cases workspace/cases/<x>.xlsx --workspace workspace --plan-only

# 完整三段(需 Playwright,可带登录态与只读库对账),批量 + 熔断
python run_three_stage.py --cases workspace/cases/<x>.xlsx --workspace workspace \
    --only TC03 --db <只读库名> --session <storageState.json> --threshold 3
```

常用参数:`--only`(逗号分隔 case_id)、`--auto-verify`(建模产物置 human_verified,仅在已走人审流程时用)、
`--db`(evidence 段对账只读库)、`--threshold`(同类问题连续失败熔断阈值,默认 3)、
`--no-breaker`、`--no-report`、`--no-resume`、`--run-dir`。

## 产物与检查点落盘

```
<run-dir>/
  <case_id>/
    artifacts/spec.json | actions.json | evidence.json   # 各段产物
    stage_checkpoint.json                                # 每段 verdict/reasons/attempts/hash
    plan_identity.json                                   # 上游产物指纹(变了即作废下游)
  reports/blocked_needs_human.jsonl                      # 熔断转人工包(触发时)
  breaker_state.json                                     # 熔断计数(可续跑)
  report.html / report.json                              # 三段汇总报告
```

## 作为库调用

```python
from core.three_stage_wiring import build_agents
from core.orchestrator import run_case
from core.stage_batch import run_batch

agents = build_agents(raw_by_case, routes=routes, kb_root=kb, caps_root=caps,
                      evidence_root=run_dir, db_name="my_ro_db")
run_case(agents, run_dir, "TC01")                 # 单条
run_batch(agents, run_dir, ["TC01", "TC02"])      # 批量 + 熔断
```

## 已知边界(刻意)

- **契约只判结构/完整性,不判业务语义**:逻辑对不对由人审 `verify_status=human_verified` 把关。
- **子 Agent 是同进程串行**:隔离靠写作用域白名单 + 上游只读(编排层隔离),非 OS 进程/会话隔离。
- **熔断只停不改判定**:同类问题连续失败达阈值 → 停批 + 转人工,沿用 `core/circuit_breaker.py` 语义。

## 测试

```powershell
python tests/test_stage_contracts... # 以下文件均可单跑或 pytest
python -m pytest tests/test_orchestrator.py tests/test_stage_adapters.py \
    tests/test_three_stage_wiring.py tests/test_stage_report.py tests/test_stage_batch.py -q
python tests/test_no_business_in_core.py   # 零业务红线(新模块均通过)
python run_tests.py                        # 统一自测(自动发现含三段式测试)
```
