"""契约规范层(通用、零业务):把不同来源(Java 源码 / OpenAPI)的接口契约统一成
一个 canonical 形态,供下游"契约 → ExecSpec 草稿 + 负例草稿"确定性消费。

canonical 形态刻意贴近 core.discovery.srcmap.build_contracts 的产物,保证旧 Java
提取链零改造即可并入;OpenAPI provider 再把 Swagger 投影到同一形态。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class ContractField:
    name: str
    type: str = "string"
    required: bool = False
    rules: list[dict[str, Any]] = field(default_factory=list)  # [{ann, arg}]


@dataclass
class ContractEndpoint:
    http: str
    path: str
    method_name: str = ""
    request_dto: str | None = None
    response: str | None = None
    fields: list[ContractField] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


@dataclass
class Contract:
    site: str
    source: str  # provider 标识:java_spring / openapi
    endpoints: list[ContractEndpoint] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"site": self.site, "source": self.source,
                "endpoints": [ep.to_dict() for ep in self.endpoints]}


def _coerce_field(raw: dict[str, Any]) -> ContractField:
    return ContractField(
        name=str(raw.get("name", "")),
        type=str(raw.get("type", "string")),
        required=bool(raw.get("required", False)),
        rules=list(raw.get("rules", []) or []),
    )


def normalize(site: str, source: str, raw_endpoints: list[dict[str, Any]]) -> Contract:
    """把 srcmap/openapi 的 dict 列表规范成 Contract。幂等、纯函数。"""
    endpoints: list[ContractEndpoint] = []
    for raw in raw_endpoints:
        endpoints.append(ContractEndpoint(
            http=str(raw.get("http", "")).upper(),
            path=str(raw.get("path", "")),
            method_name=str(raw.get("method_name", "") or ""),
            request_dto=raw.get("request_dto"),
            response=raw.get("response"),
            fields=[_coerce_field(f) for f in (raw.get("fields") or [])],
        ))
    return Contract(site=site, source=source, endpoints=endpoints)
