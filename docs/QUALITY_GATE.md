# 统一质量门禁

`quality-gate` 将产品就绪度、前置状态、业务 Oracle、运行证据和资产健康度统一为一个可用于本地或 CI 的门禁。

## 使用

```powershell
python crosscheck_cli.py quality-gate `
  --suite workspace/suites/<suite-id> `
  --workspace workspace
```

默认生成：

```text
<suite>/reports/quality_gate.json
<suite>/reports/quality_gate.md
```

门禁通过时返回 `0`，不通过时返回 `2`。不通过不是执行异常，而是当前业务套件尚未达到配置的质量标准。

## 默认门槛

默认策略面向生产回归：

- 成熟度分数不低于 `75`
- 自动化成熟度至少为 `M3`
- 前置状态准备覆盖率为 `100%`
- 业务 Oracle 覆盖率为 `100%`
- `INCONCLUSIVE` 比例不超过 `10%`
- 必须存在带运行证据的 `summary.json`
- 不允许存在 `degraded` 资产
- 不允许存在 `unhealthy` 资产

## 渐进式落地

POC 或第一批业务接入时，可以临时放宽门槛，但应将放宽写入流水线配置，而不是改变报告含义：

```powershell
python crosscheck_cli.py quality-gate `
  --suite workspace/suites/<suite-id> `
  --workspace workspace `
  --min-score 50 `
  --min-maturity M2 `
  --min-preparation 0.8 `
  --min-oracle 0.8 `
  --allow-no-run
```

放宽门槛只适合接入初期，进入正式发布门禁后应恢复默认或更严格策略。

## 阻塞项

门禁会输出机器可读的 `blockers` 和人可读的 `next_actions`，常见类型包括：

- `maturity_score`：整体成熟度分数不足
- `maturity_level`：尚未达到流水线自动回归等级
- `preparation_coverage`：缺少可执行 Fixture、State Recipe 或 Capability Pack
- `oracle_coverage`：缺少结构化业务 Oracle 或证明来源
- `inconclusive_rate`：证据不足导致无法判定的结果过多
- `run_evidence_missing`：没有真实运行摘要或 soak 证据
- `degraded_assets`：存在需要修复和重新认证的资产
- `unhealthy_assets`：存在已被隔离的资产

## 推荐 CI 顺序

```text
生成/导入用例
    ↓
product-readiness
    ↓
product-remediation
    ↓
人工审核和资产批准
    ↓
suite run / soak
    ↓
asset-health
    ↓
quality-gate
```

`quality-gate` 只负责判定和输出，不会自动批准、修复或修改资产。资产恢复必须通过 `asset-recertify` 完成。

## 门禁三档：off / observe / enforce

依据 Claude Code 团队验证方法论——新门禁应先进 observe 模式，先看误报再放量。`--mode`（默认 `enforce`）：

- `off`：不判定，直接通过（`skipped: true`）。用于临时关闭。
- `observe`：照常算 blockers，但**不阻断**（`passed: true`、退出码 0），把本会拦的项放进 `would_block`。用于新门禁上线初期核对误报、确认不影响业务。
- `enforce`（默认）：blockers 真拦（退出码 2）。

```powershell
python crosscheck_cli.py quality-gate --suite workspace/suites/<id> --workspace workspace --mode observe
```

## 验证戳（verification stamp）

每次门禁结果带一个 `verification_stamp`：`reviewed_by` / `verified_via`（如 `["quality-gate"]`，未验证则为 `["none"]`，便于查未验证的结果）/ `mode` / `passed` / `at` / `content_hash`。戳是**附加字段，不改判定**。

## diff 触发审查清单（review-gate）

`review-gate` 读**基线分支**的 `REVIEW.md`（`git show <base-ref>:REVIEW.md`，不读工作区），按当前改动命中的触发器只列相关规则（通常 3–10 条），每条带 check + incident，便于人判时不必从 diff 反推。**规则的权威版本在基线分支，改动分支里对 `REVIEW.md` 的修改不参与判定**——这是"改动不能改判它的检查"的落地。

```powershell
python crosscheck_cli.py review-gate --base-ref main
```

`rules_source` 为 `absent` 表示基线分支尚无 `REVIEW.md`（如本文件刚在改动分支新建、还未合并到 main）——这是正确行为，合并后即生效。
