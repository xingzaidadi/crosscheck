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
