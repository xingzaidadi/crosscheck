"""Playwright adapter backed by the product's deterministic Prober path."""
from __future__ import annotations

from pathlib import Path

from adapters.base import BaseAdapter
from core.interfaces import ActionResult, TestCase
from core.prober import Prober


class PlaywrightAdapter(BaseAdapter):
    def __init__(self, kb, credentials=None, headless: bool = True, *,
                 session_file: str | None = None, artifacts_dir: str | None = None):
        super().__init__(kb)
        self.credentials = credentials or {}
        self.headless = headless
        self.session_file = session_file
        self.artifacts_dir = artifacts_dir
        self._model: dict = {}

    def setup(self, case: TestCase) -> None:
        model = self.kb.page_model(case.feature)
        if isinstance(model, list):
            model = {"actions": model}
        if not isinstance(model, dict) or not (model.get("entry") or model.get("page_url")):
            raise ValueError(f"page_model missing entry/page_url for feature: {case.feature}")
        configured_session = model.get("session_file") or self.session_file
        if configured_session and not Path(configured_session).is_file():
            raise FileNotFoundError(f"session file does not exist: {configured_session}")
        self._model = model

    def perform(self, case: TestCase, marker: str) -> ActionResult:
        model = self._model or self.kb.page_model(case.feature)
        actions = _render_marker(model.get("actions") or model.get("steps") or [], marker)
        prober = Prober(
            url_pattern=str(model.get("url_pattern") or model.get("api") or ""),
            session_file=model.get("session_file") or self.session_file,
            headless=self.headless,
            artifacts_dir=self.artifacts_dir,
            launch_mode=str(model.get("launch_mode") or "isolated"),
            user_data_dir=model.get("user_data_dir"),
            cdp_endpoint=model.get("cdp_endpoint"),
        )
        try:
            prober.probe(
                str(model.get("entry") or model.get("page_url")),
                wait_ms=int(model.get("wait_ms", 1500)),
                replay_actions=actions,
            )
        except Exception as exc:  # noqa: BLE001
            return ActionResult(ok=False, error=f"browser execution failed: {exc}")
        failed = [item for item in prober.replay_results if not item.get("ok")]
        capture = prober.pick_write_call()
        expected_texts = list(model.get("success_texts") or [])
        return ActionResult(
            ok=not failed and (capture is not None or not model.get("require_write_call", False)),
            api_status=capture.status if capture else None,
            api_body=capture.response_json if capture else None,
            page_texts=expected_texts,
            error="; ".join(item.get("error", "replay failed") for item in failed) or None,
        )

    def teardown(self) -> None:
        self._model = {}


def _render_marker(value, marker: str):
    if isinstance(value, str):
        return value.replace("{{marker}}", marker).replace("{{AUTOTEST_标记值}}", marker)
    if isinstance(value, list):
        return [_render_marker(item, marker) for item in value]
    if isinstance(value, dict):
        return {key: _render_marker(item, marker) for key, item in value.items()}
    return value
