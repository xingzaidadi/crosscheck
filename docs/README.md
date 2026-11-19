# Crosscheck 文档中心

项目对外和日常维护只需要优先阅读本页列出的“现行文档”。计划、阶段审计、设计草稿和临时交接材料均已移入 `archive/`，避免与当前事实混在一起。

## 现行文档

| 文档 | 用途 | 建议 |
|---|---|---|
| `../README.md` | 项目定位、安装、快速使用和主要入口 | 首先阅读 |
| `../ARCHITECTURE.md` | 总体架构、执行流程和移植边界 | 架构入口 |
| `ONBOARDING.md` | 新业务系统接入步骤 | 接入时阅读 |
| `PRODUCT_USAGE.md` | 产品化 CLI 和操作入口 | 使用时阅读 |
| `COMPATIBILITY.md` | 正式支持范围和条件支持项 | 接入前确认 |
| `TROUBLESHOOTING.md` | 常见安装、登录、UI、API、DB 和清理问题 | 故障时阅读 |
| `RELEASE_CHECKLIST.md` | 发布门禁和交付检查 | 发布时执行 |
| `GENERAL_TOOL_ACCEPTANCE.md` | 通用能力和结果真实性验收标准 | 验收基线 |
| `IMPLEMENTATION_STATUS.md` | 当前实现状态与验证等级 | 当前事实来源 |
| `GENERAL_TOOL_ACCEPTANCE_RESULTS.md` | 自动生成的验收结果摘要 | 结果证据，避免手改 |
| `UNIFIED_DOCUMENTATION_AND_IMPLEMENTATION_PLAN.md` | 跨计划的综合设计基线 | 仅在设计追溯时阅读 |

`GENERAL_TOOL_ACCEPTANCE_RESULTS.json` 是脚本生成的数据文件，不属于手工维护文档。`external-acceptance.example.yaml` 是外部验收输入模板，继续保留在 `docs/` 根目录便于调用。

## 已归档材料

| 目录 | 内容 | 处理建议 |
|---|---|---|
| `archive/plans/` | AI 用例、业务武器库、主方案和优化路线等历史计划 | 默认不参与日常阅读；确认不再追溯后可删除 |
| `archive/audits/` | 带日期的阶段实施审计 | 可在后续审计覆盖后删除旧版本 |
| `archive/design/` | 被当前架构文档覆盖的设计稿 | 建议核对差异后删除 |
| `archive/handoffs/` | 针对单次会话或阶段的交接材料 | 临时性最强，优先确认删除 |

MiCo 集成文档仍保留在 `integrations/mico/`，它们属于独立集成功能，不与核心项目文档混排。`.agents/` 和 `.claude/` 下的 Markdown 是 Agent/Skill 运行配置，也不属于项目说明文档，不能按普通文档删除。

## 建议删除候选

以下文件已经完成归档，但本次未直接删除：

1. `archive/handoffs/HANDOFF_UI_FIRST.md`：一次性 UI-first 交接和待办记录，内容时效性强。
2. `archive/audits/PLAN_IMPLEMENTATION_AUDIT_20261115.md`：日期快照，后续已有更新状态时价值较低。
3. `archive/design/FRAMEWORK_ARCHITECTURE.md`：简短英文架构稿，与根目录 `ARCHITECTURE.md` 及实际代码说明重复。
4. `archive/plans/AI_EXECUTABLE_CASES_PLAN.md`：长篇阶段计划，核心状态已由 `IMPLEMENTATION_STATUS.md` 承接。
5. `archive/plans/BUSINESS_TEST_ARSENAL_PLAN.md`：长篇专项计划，与主方案及当前实现状态大量重叠。
6. `archive/plans/OPTIMIZATION_ROADMAP.md`：历史整改路线，完成项和当前项已不适合作为现行入口。

暂不建议直接删除 `archive/plans/CASE_ARSENAL_MASTER_PLAN.md`，因为 `IMPLEMENTATION_STATUS.md` 仍把它作为设计基线引用。待把仍有效的领域模型和阶段门禁提炼进现行架构后，再删除更稳妥。

## 维护规则

- `docs/` 根目录只放长期有效的使用、架构、兼容、验收、状态和发布文档。
- 文件名含 `PLAN`、`AUDIT`、日期、`HANDOFF` 或 `DRAFT` 的材料默认进入 `docs/archive/`。
- 当前事实只在 `IMPLEMENTATION_STATUS.md` 维护；验收标准只在 `GENERAL_TOOL_ACCEPTANCE.md` 维护。
- 自动生成结果应由脚本覆盖，不在多个计划文档中重复维护完成度。
- 删除归档文件前先搜索代码、发布脚本和现行文档中的路径引用。
