"""契约 → ExecSpec 草稿 + 负例草稿(通用、零业务):把 canonical 契约确定性翻成
可执行规格草稿,消灭"逆向猜接口"。产物是 draft(verify_status=draft),人审一次
或经 modeler 补 oracle 后才进执行——延续"不经人审不得晋级"。

两类产物:
  1. happy-path 草稿:method/url + 必填字段占位 body,断言 status<400。
  2. 负例草稿(从校验注解确定性派生):
       - @NotBlank/@NotNull/@NotEmpty → 缺该字段应被拒(期望 4xx)。
       - @Size(max=N) → 超长值应被拒。
       - @Max/@Min/@DecimalMax/@DecimalMin → 越界值应被拒。
       - @Past → 未来日期应被拒(反之 @Future)。
  负例是"该拒的有没有拒"的机器来源,正是三源对账里人眼给不了的部分。
"""
from __future__ import annotations

from typing import Any

from core.contract_ingest.canonical import Contract, ContractEndpoint, ContractField

_PLACEHOLDER = {
    "string": "AUTOTEST_x",
    "int": 1, "integer": 1, "long": 1, "Integer": 1, "Long": 1,
    "number": 1, "double": 1.0, "float": 1.0, "BigDecimal": 1,
    "bool": True, "boolean": True, "Boolean": True,
}


def _placeholder(field: ContractField) -> Any:
    base = field.type.split("<")[0]
    return _PLACEHOLDER.get(base, _PLACEHOLDER.get(base.lower(), "AUTOTEST_x"))


def _happy_body(ep: ContractEndpoint) -> dict[str, Any]:
    return {f.name: _placeholder(f) for f in ep.fields if f.required} or \
           {f.name: _placeholder(f) for f in ep.fields[:3]}


def _arg_value(arg: str, key: str) -> str | None:
    """从注解 arg(如 "max=10, message=..." 或 "10")里取某个参数值。"""
    arg = (arg or "").strip()
    if not arg:
        return None
    for part in arg.split(","):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            if k.strip() == key:
                return v.strip().strip('"')
        elif key in ("max", "value") and part.isdigit():
            return part
    return None


def _negative_drafts(ep: ContractEndpoint) -> list[dict[str, Any]]:
    drafts: list[dict[str, Any]] = []
    base = _happy_body(ep)
    for f in ep.fields:
        # 必填字段:无论来源是 Java @NotBlank 还是 OpenAPI required,都派生"缺字段应被拒"负例一次。
        required_ann = {r.get("ann") for r in f.rules} & {"NotBlank", "NotNull", "NotEmpty"}
        if f.required and not required_ann:
            body = dict(base)
            body.pop(f.name, None)
            drafts.append({
                "kind": "negative", "field": f.name, "rule": "NotNull",
                "request": {"method": ep.http, "url": ep.path, "body": body},
                "assertions": {"response": {"status_gte": 400}},
                "reason": f"缺必填字段 {f.name}(required)应被拒",
                "verify_status": "draft",
            })
        for rule in f.rules:
            ann = rule.get("ann")
            arg = rule.get("arg", "")
            body = dict(base)
            reason = None
            if ann in ("NotBlank", "NotNull", "NotEmpty"):
                body.pop(f.name, None)
                reason = f"缺必填字段 {f.name}({ann})应被拒"
            elif ann == "Size":
                mx = _arg_value(arg, "max")
                if mx and mx.isdigit():
                    body[f.name] = "x" * (int(mx) + 1)
                    reason = f"字段 {f.name} 超长(>{mx})应被拒"
            elif ann in ("Max", "DecimalMax"):
                mx = _arg_value(arg, "value") or _arg_value(arg, "max") or arg.strip().strip('"')
                if mx and mx.lstrip("-").isdigit():
                    body[f.name] = int(mx) + 1
                    reason = f"字段 {f.name} 越上界(>{mx})应被拒"
            elif ann in ("Min", "DecimalMin"):
                mn = _arg_value(arg, "value") or _arg_value(arg, "min") or arg.strip().strip('"')
                if mn and mn.lstrip("-").isdigit():
                    body[f.name] = int(mn) - 1
                    reason = f"字段 {f.name} 越下界(<{mn})应被拒"
            elif ann == "Past":
                body[f.name] = "2999-12-31"
                reason = f"字段 {f.name} 为未来日期(@Past)应被拒"
            elif ann == "Future":
                body[f.name] = "2000-01-01"
                reason = f"字段 {f.name} 为过去日期(@Future)应被拒"
            if reason:
                drafts.append({
                    "kind": "negative",
                    "field": f.name,
                    "rule": ann,
                    "request": {"method": ep.http, "url": ep.path, "body": body},
                    "assertions": {"response": {"status_gte": 400}},
                    "reason": reason,
                    "verify_status": "draft",
                })
    return drafts


def endpoint_to_drafts(ep: ContractEndpoint) -> dict[str, Any]:
    """一个端点 → {happy: ExecSpec草稿, negatives: [负例草稿]}。"""
    happy = {
        "kind": "happy_path",
        "request": {"method": ep.http, "url": ep.path, "body": _happy_body(ep)},
        "assertions": {"response": {"status_lt": 400}},
        "source_dto": ep.request_dto,
        "verify_status": "draft",
    }
    return {"endpoint": f"{ep.http} {ep.path}", "happy": happy, "negatives": _negative_drafts(ep)}


def contract_to_drafts(contract: Contract) -> dict[str, Any]:
    """整份契约 → 全部端点的草稿集合 + 统计(供 readiness 翻转与计分)。"""
    specs = [endpoint_to_drafts(ep) for ep in contract.endpoints]
    negatives = sum(len(s["negatives"]) for s in specs)
    return {
        "site": contract.site,
        "source": contract.source,
        "endpoint_count": len(specs),
        "negative_count": negatives,
        "specs": specs,
    }
