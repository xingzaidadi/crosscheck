"""B 契约→路由自动草拟(通用、零业务):读 srcmap 契约目录,为写端点批量生成 case_routes 的
write 路由骨架草稿——body 按 DTO 字段铺、已知流水线变量自动填、必填项标注待审。
把"手写路由"降为"机器出草稿、人审断言"。

零业务:字段名→变量的映射(known_var)、父键名(parent_key)由调用方(workspace)传入;
core 只知通用框架概念(幂等键/版本),不认任何领域字段名。
纯函数:endpoint_to_route、drafts_from_contracts。
"""
from __future__ import annotations

from typing import Any

# 框架通用变量映射(非领域词):幂等键、版本号是通用 HTTP/并发概念。领域字段(单号/行ID 等)
# 由调用方在 known_var 里补(workspace),core 不写死任何领域字段名。
_GENERIC_VAR = {"idempotencyKey": "{{marker}}", "version": "{{ver}}"}
# 只读/非写端点子串:不出写路由草稿
READ_HINT = ("/page", "/detail", "/list", "/query", "/count", "/export", "/download", "/tree")


def _field_value(f: dict, known_var: dict) -> Any:
    n = f.get("name", "")
    if n in known_var:
        return known_var[n]
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


def endpoint_to_route(ep: dict, context_prefix: str = "", *,
                      known_var: dict | None = None, parent_key: str = "<父键>") -> dict | None:
    """单端点契约 → 路由骨架({feature, mode:write, write:{...}})。只读端点返回 None。
    known_var:领域字段名→{{var}}(workspace 传);parent_key:父表键名(workspace 传)。"""
    kv = {**_GENERIC_VAR, **(known_var or {})}
    path = ep.get("path") or ""
    if ep.get("http") not in ("POST", "PUT", "PATCH") or any(h in path for h in READ_HINT):
        return None
    body = {f["name"]: _field_value(f, kv) for f in (ep.get("fields") or [])}
    url = path[len(context_prefix):] if context_prefix and path.startswith(context_prefix) else path
    return {
        "feature": "<待填>", "mode": "write",
        "write": {
            "request": {"method": ep["http"], "url": url, "body": body},
            "table": "<落库表>", "parent_key": parent_key, "parent_marker_col": "<标记列>",
            "assert_status": {"column": "<状态列>", "value": "<期望态>"},
            "_contract": {"dto": ep.get("request_dto"),
                          "required": [f["name"] for f in (ep.get("fields") or []) if f.get("required")]},
        }}


def drafts_from_contracts(contracts: list[dict], context_prefix: str = "", *,
                          known_var: dict | None = None, parent_key: str = "<父键>") -> dict:
    """批量:契约列表 → {端点路径: 路由骨架}(仅写端点)。"""
    out = {}
    for ep in contracts:
        r = endpoint_to_route(ep, context_prefix, known_var=known_var, parent_key=parent_key)
        if r:
            out[ep["path"]] = r
    return out
