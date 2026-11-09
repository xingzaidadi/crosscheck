"""适配器(操作·感知层)工厂收口:把 adapter 的构造从各处写死的 `ApiAdapter(...)`
统一到 registry 的 "adapter" kind。换/加驱动(ui、日后 mq/job/cli)只在此登记或由
workspace/plugins 追加,engine/events/run_batch 一律走 make_adapter(kind, **kw),内核不改——
兑现 core/interfaces.Adapter ABC 文档里"内核都不用改"的开闭承诺。
"""
from __future__ import annotations

from typing import Any

from core import registry

# 内置两种适配器工厂:**kw 原样透传各自构造签名(api 吃 base_url/session_file;ui 吃 headless 等)。
registry.register("adapter", "api", lambda **kw: _api()(**kw))
registry.register("adapter", "ui", lambda **kw: _ui()(**kw))


def _api():
    from adapters.api_adapter import ApiAdapter
    return ApiAdapter


def _ui():
    from adapters.playwright_adapter import PlaywrightAdapter
    return PlaywrightAdapter


def make_adapter(kind: str = "api", **kw) -> Any:
    """按 kind 造适配器(默认 api)。未注册的 kind 抛错并列出可选项。"""
    return registry.resolve("adapter", kind)(**kw)
