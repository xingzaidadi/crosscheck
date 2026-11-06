"""
建模层:把散文用例(RawCase)建模成可执行规格 ExecSpec。

ExecSpec 是"机器能执行、能判定"的结构:执行方式 + 目标 + 断言 + 前置/清理。
散文→ExecSpec 这步是"人工→Agent"的落点:
  - from_raw() 先做确定性草拟(分类 query/write、抽接口路径、填元数据),
    断言留空并标 _needs_review,等人工(或后续 LLM 辅助)补全;
  - verify_status 人审转 human_verified 才允许进执行。
执行期不碰 LLM,确定性回放。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import yaml

# 分类关键词(命中步骤/用例名即归类)。写优先于查(既写又查按写处理,更保守)。
_WRITE_KW = re.compile(
    r"新建|提交|暂存|创建|保存|受理|审批|撤回|驳回|编辑|修改|删除|作废|退回|关闭|转办|发起|批量|造数|初始化")
_QUERY_KW = re.compile(r"查询|列表|检索|查看|详情|筛选|搜索|分页|导出|融合|聚合")
# 接口路径:形如 /svc/api/order/create(至少两段且含 api)
_ENDPOINT = re.compile(r"/[A-Za-z0-9_\-]+(?:/[A-Za-z0-9_\-{}]+)+")


@dataclass
class ExecSpec:
    case_id: str
    title: str = ""
    level: str = ""
    category: str = ""
    kind: str = "other"             # query | write | other —— 用例做什么
    mode: str = "manual"            # reconcile | api | ui | manual —— 怎么执行
    verify_status: str = "draft"    # draft | human_verified(人审后才进执行)

    # reconcile 模式(查询类复用对账链):
    feature: str = ""               # 对应 knowledge_base/query_mapping/<feature>.json
    mapping: str = ""               # 可选:映射文件路径(默认按 feature 找)
    sample: str = ""                # 可选:抓包样本 captures/<feature>_picked.json
    db: str = ""                    # reconcile 用哪个只读库(config/db.yaml databases.<名>);空则用 default_readonly

    # 通用执行要素:
    endpoints: list[str] = field(default_factory=list)
    inputs: dict[str, Any] = field(default_factory=dict)
    assertions: dict[str, Any] = field(default_factory=dict)  # {response:{status,body:{path:val}}, db:[{table,where,row_count,fields}]}
    data_prep: list[Any] = field(default_factory=list)        # 造前置状态的请求列表(每项同 request 结构)
    cleanup: list[Any] = field(default_factory=list)          # 清理目标(按 marker 反删,子表在前):
                                                              #   {table,column} 直删;{table,key,parent:{table,key_col,marker_col}} 按父单号删子表
    allowed_tables: list[str] = field(default_factory=list)   # diff 安全网:本次允许改动的表
    diff_full_scan: bool = True                               # True=整库 diff;False=只盯 allowed∪断言表(级联写入场景免误报)

    # 写入(api)模式执行要素:
    base_url: str = ""                                        # 接口基址(默认取 profile.base_url)
    session: str = ""                                         # 登录态 storageState 文件(复用 cookie 鉴权)
    request: dict[str, Any] = field(default_factory=dict)     # 主写动作 {method,url,body,headers}
    marker_field: str = ""                                    # body 里放唯一标记的字段名(造数可识别/可清理)
    approve: dict[str, Any] = field(default_factory=dict)     # 一键审批请求(可选,同 request 结构)
    verify_poll: dict[str, Any] = field(default_factory=dict)  # 异步验库等待 {timeout_s, interval_s};空=只查一次
    prepare_state: str = ""                                    # 声明前置状态(查 state_recipes/<feature>.json 配方造单);空=不造

    # UI 渲染校验(mode=ui / reconcile 附加):证明"页面显示"== 接口(再接库对账 = 三层对齐)
    #   {page_url, url_pattern, actions[], extract:{rows_selector, columns:{domField:cellSelector}},
    #    dom_to_api:{domField:apiField}, api_rows_path, screenshot}
    ui: dict[str, Any] = field(default_factory=dict)

    source_row: int = 0
    needs_review: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def _extract_endpoints(text: str) -> list[str]:
    seen, out = set(), []
    for m in _ENDPOINT.findall(text or ""):
        if "api" in m.lower() and m not in seen:
            seen.add(m); out.append(m)
    return out


def from_raw(raw) -> ExecSpec:
    """确定性草拟:分类 + 抽接口 + 填元数据;断言留空标 _needs_review,待人审/LLM 补。"""
    blob = f"{raw.name}\n{raw.steps_text}\n{raw.expected_text}"
    if _WRITE_KW.search(blob):
        kind, mode = "write", "api"
    elif _QUERY_KW.search(blob):
        kind, mode = "query", "reconcile"
    else:
        kind, mode = "other", "manual"

    notes: list[str] = ["assertions 待人工/LLM 补全后,verify_status 改 human_verified 才进执行"]
    if "待确认" in (raw.notes or ""):
        notes.append(f"口径待确认(备注):{raw.notes[:60]}")

    return ExecSpec(
        case_id=raw.case_id, title=raw.name, level=raw.level, category=raw.category,
        kind=kind, mode=mode, verify_status="draft",
        feature="", endpoints=_extract_endpoints(blob),
        source_row=raw.row, needs_review=notes,
        raw={"preconditions": raw.preconditions, "steps": raw.steps_text,
             "expected": raw.expected_text, "notes": raw.notes, "module": raw.module},
    )


def dump_spec(spec: ExecSpec, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(asdict(spec), allow_unicode=True, sort_keys=False), encoding="utf-8")
    return p


def load_spec(path: str | Path) -> ExecSpec:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    valid = {f for f in ExecSpec.__dataclass_fields__}
    return ExecSpec(**{k: v for k, v in data.items() if k in valid})


def load_specs(dir_path: str | Path) -> list[ExecSpec]:
    d = Path(dir_path)
    if not d.exists():
        return []
    return [load_spec(p) for p in sorted(d.glob("*.yaml"))]
