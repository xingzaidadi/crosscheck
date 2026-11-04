"""
接口适配器(API-first)。能走接口校验的别开浏览器:快、稳、零 UI flaky。

适用:落库对不对这类用例,本质是调提交接口 + 查库;浏览器只是触发器,可省。
列表/检索(查询类)就用它:接口参数 → SQL WHERE → COUNT(DISTINCT) 核对。
"""
from __future__ import annotations

import httpx

from adapters.base import BaseAdapter
from core.interfaces import ActionResult, TestCase


class ApiAdapter(BaseAdapter):
    def __init__(self, kb, credentials, base_url: str):
        super().__init__(kb)
        self.credentials = credentials
        self.base_url = base_url
        self._client: httpx.Client | None = None

    def setup(self, case: TestCase) -> None:
        # TODO: 建 httpx.Client;带上测试账号鉴权头/cookie(查询类走只读账号)
        ...

    def perform(self, case: TestCase, marker: str) -> ActionResult:
        pm = self.kb.page_model(case.feature)
        # TODO: 按 pm["api"] 构造请求体(marker 代入唯一字段),发请求
        # TODO: 返回 ActionResult(api_status, api_body)
        _ = (pm, marker)
        return ActionResult(ok=False, error="TODO: ApiAdapter.perform 未实现")

    def teardown(self) -> None:
        if self._client:
            self._client.close()
