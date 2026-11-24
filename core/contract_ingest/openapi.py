"""OpenAPI / Swagger provider(通用、零业务):无后端源码时,从 openapi.json/swagger.json
投影出 canonical 契约。覆盖面从"有 Java 源码"扩到"有任意 API 文档"。

支持 OpenAPI 3.x(components.schemas + $ref)与 Swagger 2.0(definitions)。
把 schema 的 required / maxLength / minLength / maximum / minimum / pattern / format=date-past
翻成与 Java 注解同构的 rules,使下游负例生成逻辑复用同一套。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.contract_ingest.canonical import Contract, normalize

# OpenAPI schema 关键字 → 与 Java 校验注解同构的 rule(ann/arg)
_KEYWORD_TO_ANN = {
    "maxLength": "Size",      # arg=max=N
    "minLength": "Size",      # arg=min=N
    "maximum": "Max",
    "minimum": "Min",
    "pattern": "Pattern",
}


def _deref(spec: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    """解一层 $ref(components.schemas / definitions),失败返回原节点。"""
    ref = node.get("$ref")
    if not ref:
        return node
    parts = ref.lstrip("#/").split("/")
    cur: Any = spec
    for part in parts:
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return node
    return cur if isinstance(cur, dict) else node


def _schema_fields(spec: dict[str, Any], schema: dict[str, Any]) -> list[dict[str, Any]]:
    schema = _deref(spec, schema)
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    fields: list[dict[str, Any]] = []
    for name, raw in props.items():
        raw = _deref(spec, raw)
        rules: list[dict[str, Any]] = []
        for kw, ann in _KEYWORD_TO_ANN.items():
            if kw in raw:
                arg = str(raw[kw])
                if kw == "maxLength":
                    arg = f"max={raw[kw]}"
                elif kw == "minLength":
                    arg = f"min={raw[kw]}"
                rules.append({"ann": ann, "arg": arg})
        if raw.get("format") == "date" and raw.get("x-past-only"):
            rules.append({"ann": "Past", "arg": ""})
        fields.append({
            "name": name,
            "type": str(raw.get("type", "string")),
            "required": name in required,
            "rules": rules,
        })
    return fields


def _request_schema(spec: dict[str, Any], op: dict[str, Any]) -> dict[str, Any] | None:
    # OpenAPI 3: requestBody.content[*].schema
    body = op.get("requestBody")
    if isinstance(body, dict):
        content = body.get("content") or {}
        for media in content.values():
            if isinstance(media, dict) and "schema" in media:
                return media["schema"]
    # Swagger 2: parameters[in=body].schema
    for param in op.get("parameters") or []:
        if isinstance(param, dict) and param.get("in") == "body" and "schema" in param:
            return param["schema"]
    return None


def extract(spec_path: str | Path, *, site: str = "") -> Contract:
    """读 OpenAPI/Swagger 文件 → canonical Contract。"""
    path = Path(spec_path)
    spec = json.loads(path.read_text(encoding="utf-8"))
    site = site or path.stem
    raw_endpoints: list[dict[str, Any]] = []
    paths = spec.get("paths") or {}
    for url, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for http, op in methods.items():
            if http.upper() not in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
                continue
            if not isinstance(op, dict):
                continue
            schema = _request_schema(spec, op)
            fields = _schema_fields(spec, schema) if schema else []
            dto = None
            if isinstance(schema, dict) and schema.get("$ref"):
                dto = schema["$ref"].split("/")[-1]
            raw_endpoints.append({
                "http": http.upper(),
                "path": url,
                "method_name": op.get("operationId", ""),
                "request_dto": dto,
                "response": None,
                "fields": fields,
            })
    return normalize(site, "openapi", raw_endpoints)
