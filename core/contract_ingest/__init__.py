"""契约摄取(通用、零业务):统一入口 + provider 注册表。

把"读源码/读 API 文档产契约"从 workspace 散脚本上移为 core 一等能力:
  - provider `java_spring`:复用 core.discovery.srcmap.build_contracts(已有 Java 引擎)。
  - provider `openapi`   :读 openapi.json/swagger.json(无源码时的兜底)。
新增来源只需 register() 一个 provider,下游(契约→ExecSpec草稿、readiness 翻转)不改。

契约到位后,readiness 可据此把"卡在没建模"的用例从 ready:false 自动翻 true,
这是把自动建模覆盖率从 ≤35% 拉到 ≥85% 的治本闭环。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from core.contract_ingest.canonical import Contract, ContractEndpoint, ContractField, normalize
from core.contract_ingest.to_execspec import contract_to_drafts, endpoint_to_drafts

_PROVIDERS: dict[str, Callable[..., Contract]] = {}


def register(name: str, fn: Callable[..., Contract]) -> None:
    _PROVIDERS[name] = fn


def providers() -> list[str]:
    return sorted(_PROVIDERS)


def ingest(provider: str, source: str, *, site: str = "", **kwargs: Any) -> Contract:
    """按 provider 名摄取契约。source 对 java_spring 是源码根,对 openapi 是文件路径。"""
    if provider not in _PROVIDERS:
        raise KeyError(f"未知 provider: {provider};可用:{providers()}")
    return _PROVIDERS[provider](source, site=site, **kwargs)


def _java_spring(source: str, *, site: str = "", context: str = "", **_: Any) -> Contract:
    from core.discovery.srcmap import build_contracts
    src = Path(source)
    site = site or src.name
    raw = build_contracts(src, context)
    return normalize(site, "java_spring", raw)


def _openapi(source: str, *, site: str = "", **_: Any) -> Contract:
    from core.contract_ingest.openapi import extract
    return extract(source, site=site)


register("java_spring", _java_spring)
register("openapi", _openapi)

__all__ = [
    "Contract", "ContractEndpoint", "ContractField", "normalize",
    "register", "providers", "ingest",
    "contract_to_drafts", "endpoint_to_drafts",
]
