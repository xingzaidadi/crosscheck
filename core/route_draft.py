"""B 契约→路由自动草拟(通用、零业务):读 srcmap 契约目录,为写端点批量生成 case_routes 的
write 路由骨架草稿——body 按 DTO 字段铺、已知流水线变量(marker/code/ver/itemId)自动填、
必填项标注待审。把"手写路由"降为"机器出草稿、人审断言"。

纯函数:endpoint_to_route(单端点契约 → 路由片段)、drafts_from_contracts(批量)。
已知变量映射属通用约定(非业务词);断言/表名留空待人审。
"""
from __future__ import annotations

from typing import Any

# 字段名 → 已知流水线变量(prep 造数产出);通用约定,非业务
KNOWN_VAR = {
    "idempotencyKey": "{{marker}}", "demandRequestCode": "{{code}}",
    "version": "{{ver}}", "itemId": "{{itemId}}", "requestItemId": "{{itemId}}",
    "templateId": "{{assocId}}",
}
# 只读/非写端点子串:不出写路由草稿
READ_HINT = ("/page", "/detail", "/list", "/query", "/count", "/export", "/download", "/tree")


def _field_value(f: dict) -> Any:
    n = f.get("name", "")
    if n in KNOWN_VAR:
        return KNOWN_VAR[n]
    t = (f.get("type") or "").lower()
    if f.get("required"):
        return "<必填·待填>"
    if "int" in t or "long" in t:
        return 0
    if "bool" in t:
        return False
    if "list" in t:
        return []
    return ""


def endpoint_to_route(ep: dict, context_prefix: str = "") -> dict | None:
    """单端点契约 → {case_id_placeholder: {feature, mode:write, write:{...}}} 骨架。只读端点返回 None。"""
    path = ep.get("path") or ""
    if ep.get("http") not in ("POST", "PUT", "PATCH") or any(h in path for h in READ_HINT):
        return None
    body = {f["name"]: _field_value(f) for f in (ep.get("fields") or [])}
    # 路由里的 url 去掉服务上下文前缀(执行期 base_url 已含)
    url = path[len(context_prefix):] if context_prefix and path.startswith(context_prefix) else path
    return {
        "feature": "<待填>", "mode": "write",
        "write": {
            "request": {"method": ep["http"], "url": url, "body": body},
            "table": "<落库表>", "parent_key": "demand_request_code", "parent_marker_col": "request_title",
            "assert_where": "demand_request_code='{{code}}'",
            "assert_status": {"column": "<状态列>", "value": "<期望态>"},
            "_contract": {"dto": ep.get("request_dto"),
                          "required": [f["name"] for f in (ep.get("fields") or []) if f.get("required")]},
        }}


def drafts_from_contracts(contracts: list[dict], context_prefix: str = "") -> dict:
    """批量:契约列表 → {端点路径: 路由骨架}(仅写端点)。"""
    out = {}
    for ep in contracts:
        r = endpoint_to_route(ep, context_prefix)
        if r:
            out[ep["path"]] = r
    return out
