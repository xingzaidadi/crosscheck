"""UI 证据采集(通用基建)。

给任意多步 UI 场景统一产出:全程视频 + 逐步截图(含 DOM) + 接口往返(路线) + 一份清单 index.html。
零业务:只做 Playwright 采集管线,不认任何业务词。场景脚本这样用:

    from core.uicapture import ui_capture
    with ui_capture(session_file, run_dir, name="case-x") as cap:
        cap.goto(url); cap.shot("loaded")
        cap.page.click("..."); cap.shot("after-click")
    # 退出后 run_dir 下已落:NN_*.png / NN_*.html / calls.json / page@*.webm / trace.zip / index.html

设计要点:
- 视频:context 开 record_video_dir,close 时落盘(webm)。
- 路线:监听每个 xhr/fetch 的 request/response,记 method/url/status/请求体/响应体。
- 回放追溯:context.tracing 录 trace.zip(可用 playwright show-trace 打开)。
- 清单:evidence.json(机器可读) + index.html(人可看,串起截图/视频/路线)。
"""
from __future__ import annotations

import json
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterator


def _slug(s: str) -> str:
    s = re.sub(r"[^0-9A-Za-z一-鿿]+", "_", (s or "step")).strip("_")
    return s[:40] or "step"


@dataclass
class Step:
    idx: int
    label: str
    png: str
    html: str
    ts: float


@dataclass
class Call:
    url: str
    method: str
    status: int | None = None
    request_body: Any = None
    response_json: Any = None
    ts: float = field(default_factory=time.time)


class Capture:
    """采集句柄:暴露 page,并提供 shot()/goto();自动记录接口往返与步骤。"""

    def __init__(self, page, run_dir: Path, url_filter: str = "/api/"):
        self.page = page
        self.run_dir = run_dir
        self.url_filter = url_filter
        self.steps: list[Step] = []
        self.calls: list[Call] = []
        self.video_path: str | None = None
        self.trace_path: str | None = None
        self._n = 0

    # ── 驱动 ──
    def goto(self, url: str, wait_ms: int = 1500) -> None:
        try:
            self.page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception:  # noqa: BLE001
            self.page.goto(url, wait_until="domcontentloaded")
        self.page.wait_for_timeout(wait_ms)

    def shot(self, label: str) -> None:
        """截一张图 + 存 DOM,计入步骤清单。"""
        self._n += 1
        stem = f"{self._n:02d}_{_slug(label)}"
        png = self.run_dir / f"{stem}.png"
        html = self.run_dir / f"{stem}.html"
        png_ok = html_ok = False
        try:
            self.page.screenshot(path=str(png), full_page=True); png_ok = True
        except Exception:  # noqa: BLE001
            pass
        try:
            html.write_text(self.page.content(), encoding="utf-8"); html_ok = True
        except Exception:  # noqa: BLE001
            pass
        self.steps.append(Step(self._n, label,
                               png.name if png_ok else "",
                               html.name if html_ok else "", time.time()))

    # ── 路线(接口往返)──
    def _on_response(self, response) -> None:
        try:
            req = response.request
            if req.resource_type not in ("xhr", "fetch"):
                return
            if self.url_filter and self.url_filter not in response.url:
                return
            try:
                post = req.post_data
                body = json.loads(post) if post else None
            except Exception:  # noqa: BLE001
                body = req.post_data
            try:
                rj = response.json()
            except Exception:  # noqa: BLE001
                rj = None
            self.calls.append(Call(url=response.url, method=req.method,
                                   status=response.status, request_body=body,
                                   response_json=rj))
        except Exception:  # noqa: BLE001
            pass


@contextmanager
def ui_capture(session_file: str | None, run_dir: str | Path, *, name: str = "case",
               headless: bool = True, record_video: bool = True, trace: bool = True,
               url_filter: str = "/api/", viewport: dict | None = None) -> Iterator[Capture]:
    """打开一个带全程录制的浏览器会话,交回采集句柄;退出时落盘并写清单。"""
    from playwright.sync_api import sync_playwright  # 延迟导入

    rd = Path(run_dir); rd.mkdir(parents=True, exist_ok=True)
    vp = viewport or {"width": 1680, "height": 1000}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx_kwargs: dict[str, Any] = {"viewport": vp}
        if session_file and Path(session_file).exists():
            ctx_kwargs["storage_state"] = session_file
        if record_video:
            ctx_kwargs["record_video_dir"] = str(rd)
            ctx_kwargs["record_video_size"] = vp
        context = browser.new_context(**ctx_kwargs)
        if trace:
            try:
                context.tracing.start(screenshots=True, snapshots=True, sources=False)
            except Exception:  # noqa: BLE001
                trace = False
        page = context.new_page()
        cap = Capture(page, rd, url_filter=url_filter)
        context.on("response", cap._on_response)
        err: Exception | None = None
        try:
            yield cap
        except Exception as e:  # noqa: BLE001  场景异常也要把已采集证据落盘
            err = e
        finally:
            if trace:
                try:
                    tp = rd / "trace.zip"; context.tracing.stop(path=str(tp)); cap.trace_path = tp.name
                except Exception:  # noqa: BLE001
                    cap.trace_path = None
            if record_video:
                try:
                    cap.video_path = Path(page.video.path()).name
                except Exception:  # noqa: BLE001
                    cap.video_path = None
            try:
                context.close()   # 视频在此落盘
            except Exception:  # noqa: BLE001
                pass
            try:
                browser.close()
            except Exception:  # noqa: BLE001
                pass
            _write_manifest(cap, rd, name)
        if err is not None:
            raise err


def _write_manifest(cap: Capture, rd: Path, name: str) -> None:
    (rd / "calls.json").write_text(
        json.dumps([asdict(c) for c in cap.calls], ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {
        "name": name,
        "ts": time.time(),
        "steps": [asdict(s) for s in cap.steps],
        "calls": len(cap.calls),
        "video": cap.video_path,
        "trace": cap.trace_path,
    }
    (rd / "evidence.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_index_html(cap, rd, name)


def _esc(s: Any) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _write_index_html(cap: Capture, rd: Path, name: str) -> None:
    parts = [f"<!doctype html><meta charset='utf-8'><title>{_esc(name)} 证据</title>",
             "<style>body{font:14px/1.5 system-ui,Segoe UI,Arial;margin:24px;color:#222}"
             "h2{margin-top:28px}img{max-width:100%;border:1px solid #ddd;border-radius:6px}"
             "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:6px;font-size:12px;vertical-align:top}"
             ".ok{color:#0a0}.bad{color:#c00}code{background:#f5f5f5;padding:1px 4px;border-radius:3px}</style>",
             f"<h1>{_esc(name)} · UI 证据</h1>"]
    if cap.video_path:
        parts.append(f"<p>全程视频:<a href='{_esc(cap.video_path)}'>{_esc(cap.video_path)}</a>"
                     f"<br><video src='{_esc(cap.video_path)}' controls style='max-width:800px'></video></p>")
    if cap.trace_path:
        parts.append(f"<p>回放 trace:<code>npx playwright show-trace {_esc(cap.trace_path)}</code></p>")
    parts.append("<h2>步骤截图</h2>")
    for s in cap.steps:
        parts.append(f"<h3>{s.idx:02d} · {_esc(s.label)}</h3>")
        if s.png:
            parts.append(f"<a href='{_esc(s.png)}'><img src='{_esc(s.png)}'></a>")
        if s.html:
            parts.append(f"<div><a href='{_esc(s.html)}'>DOM 快照</a></div>")
    parts.append(f"<h2>接口往返(路线 · {len(cap.calls)} 条)</h2>")
    parts.append("<table><tr><th>#</th><th>method</th><th>url</th><th>status</th><th>响应摘要</th></tr>")
    for i, c in enumerate(cap.calls, 1):
        summ = _esc(json.dumps(c.response_json, ensure_ascii=False))[:160] if c.response_json is not None else ""
        cls = "ok" if (c.status and c.status < 400) else "bad"
        parts.append(f"<tr><td>{i}</td><td>{_esc(c.method)}</td><td>{_esc(c.url)}</td>"
                     f"<td class='{cls}'>{_esc(c.status)}</td><td>{summ}</td></tr>")
    parts.append("</table>")
    (rd / "index.html").write_text("\n".join(parts), encoding="utf-8")
