"""走单对账·执行保真度打分(通用基建,零业务,纯函数)。

一条用例跑完,按"同一笔动作从页面走通、到接口、到落库、全链一致、证据齐"给 0-100 分,
并给每个维度的得分理由(可解释、可审计)。维度键全中性,权重/阈值从 workspace 配置读。

五个中性维度:
  ui_driven    被测写动作由页面触发(录到的接口往返里有该写调用)
  api_layer    该写请求的接口响应符合期望
  db_layer     按唯一标记查到预期落库
  consistency  页面/接口/库三处指向同一标记(同单)
  evidence     证据齐(视频 + 分步截图 + 接口路线 + 回放)

每个维度在 dims_input 里给 {"ok": True/False/None, "reason": "..."}:
  ok=None 表示该维度对本用例"不适用"(例如纯接口+库类用例无 ui_driven),
  不计入分母、不倒扣——只据适用维度归一化到 100。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from typing import Any

# 默认权重(workspace/config/scoring.yaml 可覆盖)
DEFAULT_WEIGHTS: dict[str, int] = {
    "ui_driven": 40, "api_layer": 20, "db_layer": 20, "consistency": 10, "evidence": 10,
}
# 默认分档(从高到低,取第一个满足 score>=cut 的档)
DEFAULT_BANDS: list[tuple[str, int]] = [("A", 90), ("B", 75), ("C", 60), ("D", 0)]
DIM_ORDER = ["ui_driven", "api_layer", "db_layer", "consistency", "evidence"]


@dataclass
class Dim:
    name: str
    got: float
    max: float
    applicable: bool
    ok: bool | None
    reason: str = ""


@dataclass
class Fidelity:
    score: int                       # 0-100,按适用维度归一
    grade: str                       # A/B/C/D(或配置档名)
    dims: list = field(default_factory=list)   # [Dim...] 明细,报告/审计展开

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def _grade(score: int, bands: list[tuple[str, int]] | None) -> str:
    for name, cut in (bands or DEFAULT_BANDS):
        if score >= cut:
            return name
    return (bands or DEFAULT_BANDS)[-1][0]


def score_case(dims_input: dict[str, dict], *, weights: dict[str, int] | None = None,
               grade_bands: list[tuple[str, int]] | None = None) -> Fidelity:
    """按维度打分并归一。dims_input: {dim_name: {"ok": True/False/None, "reason": str}}。

    - ok is None 或维度缺失 → 该维度不适用,不进分母。
    - 适用维度全满 → 100;无任何适用维度 → 0 分、档位取最低。
    """
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update({k: int(v) for k, v in weights.items() if k in w})
    dims: list[Dim] = []
    got_sum = 0.0
    max_sum = 0.0
    for name in DIM_ORDER:
        mx = w.get(name, 0)
        cell = dims_input.get(name) or {}
        ok = cell.get("ok", None)
        reason = cell.get("reason", "")
        applicable = ok is not None
        got = (mx if ok else 0) if applicable else 0
        if applicable:
            got_sum += got
            max_sum += mx
        dims.append(Dim(name=name, got=got, max=mx, applicable=applicable, ok=ok, reason=reason))
    score = int(round(100 * got_sum / max_sum)) if max_sum > 0 else 0
    return Fidelity(score=score, grade=_grade(score, grade_bands), dims=dims)


def build_dims(*, expect_ui: bool, ui_triggered: bool | None,
               api_ok: bool | None, db_ok: bool | None,
               consistent: bool | None, evidence_ok: bool | None,
               require_api: bool = False, require_db: bool = False) -> dict[str, dict]:
    """把执行器已知的信号组织成 score_case 的 dims_input。
    任一信号给 None 表示该维度对本用例不适用(不计分母)。
    require_api/require_db=True 时,该腿即使信号缺失也判"腿缺失=未达标"(不许靠不检查白拿满分)——
    走单对账要求"看接口"+"看数据库"两腿都真跑到。"""
    def cell(ok, yes, no):
        if ok is None:
            return {"ok": None, "reason": "本用例不适用,不计该维度"}
        return {"ok": bool(ok), "reason": yes if ok else no}

    if expect_ui:
        ui = cell(bool(ui_triggered), "页面驱动了被测写动作(录到该写调用)",
                  "声明走单却未录到 UI 触发的写调用(疑似接口建单/页面未驱动)")
    else:
        ui = {"ok": None, "reason": "非走单类(接口+库),不计 UI 驱动维度"}

    if api_ok is None and require_api:
        api = {"ok": False, "reason": "未见提交接口层,『看接口』这一腿缺失"}
    else:
        api = cell(api_ok, "写接口响应符合期望", "写接口响应不符合期望/未成立")

    if db_ok is None and require_db:
        db = {"ok": False, "reason": "未声明/未校验库断言,『看数据库』这一腿缺失(对账不完整)"}
    else:
        db = cell(db_ok, "按标记查到预期落库", "按标记未查到预期落库")

    return {
        "ui_driven": ui, "api_layer": api, "db_layer": db,
        "consistency": cell(consistent, "页面/接口/库指向同一标记(同单)", "三源未指向同一标记"),
        "evidence": cell(evidence_ok, "证据齐", "证据不全"),
    }


_DIM_CN = {"ui_driven": "UI 驱动", "api_layer": "接口层", "db_layer": "库层",
           "consistency": "三源同单", "evidence": "证据齐全"}


def score_layer(fid: dict, pass_score: int = 60) -> dict:
    """把打分结果渲染成报告里的一个 layer card(复用 cols/rows 明细表形状)。"""
    score = int(fid.get("score", 0)); grade = fid.get("grade", "")
    rows = []
    for d in fid.get("dims", []):
        appl = d.get("applicable")
        mark = "—" if not appl else ("✓" if d.get("ok") else "✗")
        rows.append([_DIM_CN.get(d.get("name"), d.get("name")),
                     "适用" if appl else "不适用",
                     f"{int(d.get('got',0))}/{int(d.get('max',0))}",
                     d.get("reason", ""), mark])
    return {"name": f"走单对账评分 {score}/100 · {grade}", "ok": score >= pass_score,
            "expected": f"执行保真度 ≥ {pass_score}(走通对账链的程度:页面走通·接口·库·同单·证据;与功能通过/失败无关)",
            "actual": f"得分 {score}/100,档位 {grade}",
            "cols": ["维度", "适用性", "得分", "理由", "判定"], "rows": rows}


def tri_source_consistent(marker: str, request_body: Any, page_drove: bool,
                          db_matched: bool) -> tuple[bool, dict[str, bool]]:
    """三源同单做实:同一张单要在【页面驱动】【接口写请求体】【库】三处对得上。
    - page_drove:页面确实触发了这次写(录到写调用)。
    - marker_in_request:本次标记字面出现在写请求体里(证明接口打的是这张单,不是接口另造)。
    - db_matched:声明的库断言命中(该单的效果落库;标题类断言按标记命中=字面 marker 入库,
      状态类断言按单号命中=该单状态已变)。诚实区分:db_matched 不等于"marker 字面入库",
      它是"这张单的库断言成立",审计里原样记录各源命中,不夸大。
    返回 (是否一致, 各源命中详情)。"""
    import json as _json
    try:
        blob = _json.dumps(request_body, ensure_ascii=False, default=str) if request_body is not None else ""
    except Exception:  # noqa: BLE001
        blob = str(request_body)
    in_request = bool(marker) and marker in blob
    sources = {"page_drove": bool(page_drove), "marker_in_request": in_request, "db_matched": bool(db_matched)}
    return (sources["page_drove"] and in_request and sources["db_matched"]), sources


def load_scoring() -> tuple[dict[str, int], list[tuple[str, int]], dict[str, Any]]:
    """从 workspace/config/scoring.yaml 读权重/分档/开关;缺省用内置默认。
    返回 (weights, bands, options)。options 含 strict_walk 等开关。"""
    try:
        from core.config import _load
        cfg = _load("scoring.yaml") or {}
    except Exception:  # noqa: BLE001
        cfg = {}
    weights = dict(DEFAULT_WEIGHTS)
    for k, v in (cfg.get("weights") or {}).items():
        if k in weights:
            weights[k] = int(v)
    bands_cfg = cfg.get("grades") or cfg.get("bands")
    if isinstance(bands_cfg, list) and bands_cfg:
        bands = [(str(b[0]), int(b[1])) for b in bands_cfg]
    elif isinstance(bands_cfg, dict) and bands_cfg:
        bands = sorted(((str(k), int(v)) for k, v in bands_cfg.items()), key=lambda x: -x[1])
    else:
        bands = list(DEFAULT_BANDS)
    options = {k: v for k, v in cfg.items() if k not in ("weights", "grades", "bands")}
    return weights, bands, options


def is_strict(options: dict[str, Any]) -> bool:
    """门禁(Stage 2)是否开启:scoring.yaml 的 strict_walk,或环境变量 CROSSCHECK_STRICT_WALK。
    默认关 —— 只打分+标注,不改 verdict。"""
    env = str(os.environ.get("CROSSCHECK_STRICT_WALK", "")).lower()
    return bool(options.get("strict_walk")) or env in ("1", "true", "yes", "on")
