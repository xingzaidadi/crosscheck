"""
接口适配器(API-first)。能走接口校验的别开浏览器。
列表/检索(查询类)用对账链;写入类(新建/提交/暂存)用它发请求、截响应 → ActionResult。

鉴权:复用登录态 storageState(.auth/<site>.json)里的 cookie,无需账密明文。
唯一标记:请求体里 {{AUTOTEST_标记值}} 占位统一替换成本次 marker;或指定 marker_field 直接写入。
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from adapters.base import BaseAdapter
from core.interfaces import ActionResult, TestCase

_MARKER_PH = "{{AUTOTEST_标记值}}"


class ApiAdapter(BaseAdapter):
    def __init__(self, kb=None, credentials: dict | None = None,
                 base_url: str = "", session_file: str | None = None, timeout: int = 20):
        super().__init__(kb)
        self.credentials = credentials or {}
        self.base_url = (base_url or "").rstrip("/")
        self.session_file = session_file
        self.timeout = timeout
        self._client = None

    def setup(self, case: TestCase | None = None) -> None:
        import httpx  # 延迟导入
        self._client = httpx.Client(
            base_url=self.base_url, timeout=self.timeout,
            cookies=self._load_cookies(), follow_redirects=True)

    def _load_cookies(self) -> dict:
        if not self.session_file or not Path(self.session_file).exists():
            return {}
        try:
            state = json.loads(Path(self.session_file).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
        return {c["name"]: c["value"] for c in (state.get("cookies") or []) if "name" in c}

    @staticmethod
    def _inject_marker(body: Any, marker_field: str | None, marker: str) -> Any:
        if body is None:
            return None
        def walk(x):
            if isinstance(x, str):
                return x.replace(_MARKER_PH, marker)
            if isinstance(x, dict):
                return {k: walk(v) for k, v in x.items()}
            if isinstance(x, list):
                return [walk(v) for v in x]
            return x
        b = walk(copy.deepcopy(body))
        if marker_field and isinstance(b, dict):
            b[marker_field] = marker
        return b

    def call(self, request: dict, marker: str) -> ActionResult:
        """发一个请求(主动作 / 造数 / 审批都走它)。marker 注入 body。"""
        if self._client is None:
            self.setup()
        method = (request.get("method") or "GET").upper()
        url = request.get("url") or "/"
        headers = request.get("headers") or {}
        body = self._inject_marker(request.get("body"), request.get("marker_field"), marker)
        try:
            if method in ("GET", "DELETE"):
                resp = self._client.request(method, url, params=body or None, headers=headers)
            else:
                resp = self._client.request(method, url, json=body, headers=headers)
        except Exception as e:  # noqa: BLE001
            return ActionResult(ok=False, error=f"请求异常: {e}")
        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            data = resp.text
        return ActionResult(ok=resp.status_code < 400, api_status=resp.status_code, api_body=data)

    def perform(self, case: TestCase, marker: str) -> ActionResult:
        raw = case.raw or {}
        request = dict(raw.get("request") or {})
        if not request:
            return ActionResult(ok=False, error="spec 无 request,无法执行写动作")
        if raw.get("marker_field") and "marker_field" not in request:
            request["marker_field"] = raw["marker_field"]
        return self.call(request, marker)

    def teardown(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
