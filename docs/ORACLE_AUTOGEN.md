# 业务 Oracle 自动生成器(设计稿 · 待评审 · 暂不落代码)

> 目标:补上工具的头号缺口——"逻辑对不对"的**自动判定依据**(业务 Oracle),
> 把跨层对账从"人审一次建模"往"机器先产候选、人只复核"推进。
>
> 定位:**只产候选、带置信度与证据、喂进现有 review/human_verified 流程,绝不自动放开人审闸。**
> 零业务、确定性、可测;执行期不碰 LLM(与全仓一致)。

## 1. 为什么是它(而不是先做"自动过闸")

当前 `--plan-only` 实测:真实用例在 CP-1 被打回的两大理由是
`无可判定依据(assertions/ui/request 均空)` 和 `verify_status 非 human_verified`。

根因是**断言是空的**。所以即便先放开人审闸(机器代签 human_verified),机器也判不了对错,
等于把"瞎猜"合法化。正确顺序:

```
先让机器能产出可判定断言(本设计) → 再谈带置信度阈值+审计的自动过闸(后续,另评审)
```

## 2. 不重复造轮子:复用已有积木

| 已有能力 | 本设计如何复用 |
|---|---|
| `core/oracle.py` 确定性 oracle schema(`subject/operator/expected`)+ 评估器 | 生成器**产出这个格式**,不发明新格式 |
| `core/adversarial.py` 从库约束派生负向用例 | 负向 Oracle 已覆盖,生成器**只补正向** |
| `core/assertion_knowledge.py` 把预期文本绑到已审资产 | 生成器产候选后,**仍走这套绑定/审核** |
| `core/oracle_readiness.py` 评估 oracle 就绪度 | 生成器产物**接受它的就绪评估** |
| `core/discovery/fields.py` / `db_intel` 库约束 | 作为 DB 侧 Oracle 的**证据来源** |

## 3. 输入 / 输出

**输入(三类证据,都是确定性来源,非 LLM):**
- 用例预期文本 `expected_text`(RawCase);
- 接口契约:抓包样本 `captures/<feature>_picked.json` + 查询映射 `knowledge_base/query_mapping/<feature>.json`;
- 库约束:`discovery/db_intel` 的表/列/枚举/非空。

**输出:候选 Oracle 列表**,每条:
```json
{
  "id": "auto-ui-1",
  "layer": "ui | api | db",
  "subject": "data.total",          // oracle.py 的点路径
  "operator": "gte",                 // 复用 oracle.py 支持的算子
  "expected": 1,
  "confidence": 0.82,                // 0~1,见 §4
  "source": "expected_text:\"列表至少一条\" + api:data.total",
  "evidence_refs": ["captures/x_picked.json#data.total"],
  "status": "candidate"              // 永远是 candidate,绝不是 human_verified
}
```

## 4. 置信度(确定性打分,不玄学)

置信度是**可解释的加法分**,每一分都能回溯到一条确定性依据:

| 依据 | 加分 | 说明 |
|---|---|---|
| 预期文本命中结构化模式(如"显示/至少N条/状态为X") | +0.4 | 规则表在 workspace,core 不认领域词 |
| subject 能在抓包样本里找到实际路径 | +0.3 | 路径存在=可判定 |
| expected 值能从文本或库约束确定(枚举/范围/常量) | +0.2 | 否则留空→低分 |
| 已审查询映射支持该字段 | +0.1 | 与 assertion_knowledge 一致 |

- `confidence >= 高阈值`:进 review 队列置顶(最可能被人一眼通过);
- `confidence < 低阈值`:仍产出,但标记"证据不足,需人工补 expected";
- **任何分数都不自动置 human_verified**——阈值只影响排序与提示,不影响闸。

## 5. 与 CP-1 / 人审闸的关系(安全边界)

```
生成器 → 候选 Oracle(status=candidate, 带 confidence/证据)
        → 写入 workspace(待审),CP-1 仍要求 human_verified
        → 人复核(复核成本从"从零写断言"降到"看机器提案点是/否")
        → 通过后 verify_status=human_verified → 进执行
```

**三条红线:**
1. 生成器**只写 workspace 候选区**,不碰 `verify_status`、不改判定规则。
2. core 零业务:所有领域词模式放 `workspace/config/oracle_patterns.yaml`,core 只做"按规则抽取"。
3. 证据哈希:每条候选带 `evidence_refs`,无证据的 expected 判低置信、标注,不混入高分。

## 6. 落地模块(评审通过后才写)

| 文件 | 职责 |
|---|---|
| `core/oracle_autogen.py` | 纯函数:`generate(expected_text, api_sample, db_constraints, rules) -> list[候选 Oracle]` + `score()` |
| `workspace/config/oracle_patterns.yaml` | 领域文本模式(业务侧,可换) |
| 接入点 | `core/modeler.py` 建模时把候选写进 `spec.assertions`(标 candidate),供 `assertion_knowledge` 绑定与人审 |
| 测试 | `tests/test_oracle_autogen.py`:正向抽取、置信度打分、零业务、与 oracle.py 评估器端到端 |

## 7. 验收标准(定义"做成了")

- 对真实用例,生成器能对**查询/展示类**预期产出可判定正向 Oracle,`oracle.py` 能直接评估;
- 候选全部 `status=candidate`,CP-1 仍打回未审的,**人审闸未被绕过**(回归可证);
- 零业务门禁通过;置信度打分可解释、可测;
- 人复核工作量下降(从"写断言"变"点通过"),但判定权仍在人。

## 8. 明确不做(范围边界)

- 不做写入/审批类复杂业务流的 Oracle(需状态机/补偿,属 M3 范畴);
- 不做"自动放开 human_verified"(单独评审,本设计是其前置);
- 不引入执行期 LLM。
