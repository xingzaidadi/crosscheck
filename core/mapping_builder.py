"""
自动建模器:把一次捕获样本(请求参数 + 返回 JSON)+ 库表字段,推成 query_mapping 草稿。

做的事:
  - 请求参数名 → 库列名:camelCase→snake_case 归一化后匹配;匹配不上标 _needs_review。
  - 从返回结构自动识别分组计数(statusGroups 之类)和结果列表路径。
  - compare_fields 取"返回行字段 ∩ 库列"。
人只在最后审一次这份草稿(把 _needs_review 的补齐、确认 op),审完 verify_status 转 human_verified。
这样人给的只有 URL,其余由工具产出。
"""
from __future__ import annotations

import re
from typing import Any

from core.prober import Capture


def camel_to_snake(s: str) -> str:
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", s)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()


def _match_column(param: str, columns: list[str]) -> str | None:
    """参数名匹配库列:原名 / snake 化 / 去下划线 三级,命中即返回列名。"""
    cols_lower = {c.lower(): c for c in columns}
    candidates = {param.lower(), camel_to_snake(param).lower(),
                  param.lower().replace("_", "")}
    for cand in candidates:
        if cand in cols_lower:
            return cols_lower[cand]
    # 去下划线再比一轮
    squashed = {c.lower().replace("_", ""): c for c in columns}
    for cand in candidates:
        if cand.replace("_", "") in squashed:
            return squashed[cand.replace("_", "")]
    return None


def _flatten_params(capture: Capture) -> dict[str, Any]:
    """合并 query 参数和 JSON 请求体的顶层字段,作为候选检索参数。"""
    params: dict[str, Any] = {}
    params.update(capture.query_params or {})
    body = capture.request_body
    if isinstance(body, dict):
        for k, v in body.items():
            # 跳过分页等非筛选参数(建模草稿里排除,减少噪音)
            if k.lower() in ("page", "pagesize", "pagenum", "pageno", "offset", "limit", "size"):
                continue
            params[k] = v
    return params


def _detect_group_by(resp: Any) -> dict | None:
    """在返回里找形如 [{<key>: x, count: n}, ...] 的分组计数结构。"""
    data = resp.get("data") if isinstance(resp, dict) else None
    if not isinstance(data, dict):
        return None
    for key, node in data.items():
        if isinstance(node, list) and node and isinstance(node[0], dict):
            keys = set(node[0].keys())
            count_field = next((k for k in keys if k.lower() in ("count", "total", "num", "cnt")), None)
            group_field = next((k for k in keys if k != count_field), None)
            if count_field and group_field:
                return {
                    "response_path": f"data.{key}",
                    "group_key_field": group_field,
                    "group_count_field": count_field,
                    "sql_group_column": camel_to_snake(group_field),
                    "_needs_review": "确认 sql_group_column 是否为真实库列",
                }
    return None


def _detect_rows(resp: Any) -> list[dict]:
    data = resp.get("data") if isinstance(resp, dict) else None
    if isinstance(data, dict):
        for k in ("list", "rows", "records"):
            if isinstance(data.get(k), list):
                return data[k]
    if isinstance(data, list):
        return data
    return []


def build_mapping_draft(
    capture: Capture,
    db_name: str,
    table: str,
    pk: str,
    columns: list[str],
) -> dict[str, Any]:
    """产出 query_mapping 草稿。所有自动推断处带 verify_status / _needs_review 标注。"""
    params = _flatten_params(capture)
    param_map: dict[str, Any] = {}
    review_notes: list[str] = []

    for name, value in params.items():
        col = _match_column(name, columns)
        op = "in" if isinstance(value, (list, tuple)) else (
            "like" if isinstance(value, str) else "eq")
        entry: dict[str, Any] = {"column": col or f"TODO_{camel_to_snake(name)}", "op": op}
        if op == "like":
            entry["wrap"] = "%{v}%"
        if col is None:
            entry["_needs_review"] = "未在库表找到对应列,请人工指定"
            review_notes.append(f"参数 {name!r} 未匹配到列")
        param_map[name] = entry

    rows = _detect_rows(capture.response_json)
    row_keys = list(rows[0].keys()) if rows and isinstance(rows[0], dict) else []

    # 接口返回行字段 → 库列名映射。能语法匹配上的(classificationType→classification_type)自动填;
    # 语义型(如 itemName→name、itemId→id)机器猜不出,留给人审 —— 这是对账字段比对的前提。
    response_field_map: dict[str, str] = {}
    compare_fields: list[str] = []
    for k in row_keys:
        col = _match_column(k, columns)
        if col:
            if col != k:
                response_field_map[col] = k
            compare_fields.append(col)
        else:
            review_notes.append(f"返回字段 {k!r} 未自动匹配到库列,若要纳入字段比对请在 response_field_map 补 <库列>:{k!r}")
    # 接口主键字段名常与库 pk 不同(如 itemId vs id),显式提示人审
    pk_api_guess = next((k for k in row_keys if _match_column(k, [pk]) or k.lower().endswith(pk.lower())), None)
    if pk_api_guess and pk_api_guess != pk:
        response_field_map.setdefault(pk, pk_api_guess)

    group_by = _detect_group_by(capture.response_json)
    total_check = None if group_by else _detect_total(capture.response_json)

    draft = {
        "feature": "列表检索",
        "db": db_name,
        "table": table,
        "table_alias": "v",
        "pk": pk,
        "_source": {"url": capture.url, "method": capture.method},
        "verify_status": "auto_discovered_pending",
        "fixed_where": "TODO: 固定条件如 v.tenant_id / v.delete_status,请人工确认(列名带表别名 v.)",
        "joins": [],
        "_joins_hint": "若某个接口参数(如某关联维度的 code)落在关联表而非主表,"
                       "在此加 {type,table,alias,on},并把对应 param_map 的 column 指到 <别名>.<列>。"
                       "有 join 时数量核对自动走 COUNT(DISTINCT 主键)。",
        "param_map": param_map,
        "group_by": group_by,
        "total_check": total_check,
        "response_field_map": response_field_map,
        "field_sample_check": {"sample_size": 5, "compare_fields": compare_fields},
        "_review_notes": review_notes or ["自动匹配全部命中,仍需人工确认 op / fixed_where / joins"],
    }
    return draft


def _detect_total(resp: Any) -> dict | None:
    """无分组时,找返回里的总数字段(data.total / totalCount / count),用于总数核对。"""
    data = resp.get("data") if isinstance(resp, dict) else None
    if not isinstance(data, dict):
        return None
    for key in ("total", "totalCount", "count", "searchCount"):
        if isinstance(data.get(key), (int, float)):
            return {"response_path": f"data.{key}",
                    "_needs_review": "确认该字段是'去重后总数'而非'当前页数'"}
    return None
