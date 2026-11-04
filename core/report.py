"""
测试报告(HTML,自包含)。把一次运行的四类证据串成一页:
  流程视频(给人看) + 关键步骤截图 + 抓到的检索接口请求/响应(真值) + 连库对账结论。

视频是"给人看流程",接口样本 + 对账才是"能判对错的证据" —— 报告把两者放一起,
让人既能回看操作,又能看到机器对出来的一致/不一致。
"""
from __future__ import annotations

import base64
import html
import json
from pathlib import Path
from typing import Any


def _pre(obj: Any) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:  # noqa: BLE001
        s = str(obj)
    return f"<pre>{html.escape(s)}</pre>"


def _img_b64(path: str) -> str:
    try:
        data = Path(path).read_bytes()
        return "data:image/png;base64," + base64.b64encode(data).decode()
    except Exception:  # noqa: BLE001
        return ""


def build_report(
    out_path: str | Path,
    *,
    feature: str,
    site: str,
    page_url: str,
    picked: dict | None = None,
    reconcile_text: str | None = None,
    consistent: bool | None = None,
    screenshots: list[dict] | None = None,
    video_path: str | None = None,
    capture_count: int = 0,
) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if consistent is True:
        badge = '<span class="ok">对账一致 ✓</span>'
    elif consistent is False:
        badge = '<span class="bad">对账不一致 ✗</span>'
    else:
        badge = '<span class="muted">未对账</span>'

    # 视频用相对路径链接(webm 可能较大,不内联)
    video_html = '<p class="muted">本次未录制视频</p>'
    if video_path and Path(video_path).exists():
        try:
            rel = Path(video_path).relative_to(out.parent)
        except ValueError:
            rel = Path(video_path)
        video_html = (f'<video controls width="900" src="{html.escape(str(rel))}"></video>'
                      f'<p class="muted">{html.escape(str(video_path))}</p>')

    shots_html = ""
    for s in (screenshots or []):
        b64 = _img_b64(s["path"])
        if b64:
            shots_html += (f'<figure><img src="{b64}"/>'
                           f'<figcaption>{html.escape(s["name"])}</figcaption></figure>')

    api_html = '<p class="muted">未认出检索接口</p>'
    if picked:
        api_html = (
            f'<p><b>{html.escape(str(picked.get("method","")))}</b> '
            f'{html.escape(str(picked.get("url","")))}</p>'
            f'<h4>请求参数</h4>{_pre(picked.get("request_body") or picked.get("query_params") or {})}'
            f'<h4>返回 JSON</h4>{_pre(picked.get("response_json") or {})}'
        )

    recon_html = (f'<pre>{html.escape(reconcile_text)}</pre>'
                  if reconcile_text else '<p class="muted">本次未连库对账</p>')

    doc = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>测试报告 · {html.escape(feature)}</title>
<style>
 body{{font:14px/1.6 -apple-system,Segoe UI,Microsoft YaHei,sans-serif;margin:0;background:#f6f7f9;color:#1a1a1a}}
 .wrap{{max-width:1000px;margin:0 auto;padding:24px}}
 h1{{font-size:20px;margin:0 0 4px}} h2{{font-size:16px;margin:28px 0 8px;border-left:3px solid #4a6cf7;padding-left:8px}}
 h4{{margin:12px 0 4px;color:#555}}
 .meta{{color:#666;font-size:13px}} .muted{{color:#999}}
 .ok{{background:#e6f7ea;color:#137333;padding:2px 10px;border-radius:12px;font-weight:600}}
 .bad{{background:#fce8e6;color:#c5221f;padding:2px 10px;border-radius:12px;font-weight:600}}
 pre{{background:#fff;border:1px solid #e3e5e8;border-radius:6px;padding:12px;overflow:auto;max-height:420px;font:12px/1.5 Consolas,monospace}}
 figure{{margin:0 0 16px}} img{{max-width:100%;border:1px solid #ddd;border-radius:6px}}
 figcaption{{color:#666;font-size:12px;margin-top:4px}}
 video{{border:1px solid #ddd;border-radius:6px;background:#000}}
 .card{{background:#fff;border:1px solid #e3e5e8;border-radius:8px;padding:16px;margin-top:8px}}
</style></head><body><div class="wrap">
<h1>测试报告 · {html.escape(feature)} &nbsp; {badge}</h1>
<p class="meta">站点 {html.escape(site)} · 页面 {html.escape(page_url)} · 本次抓到 {capture_count} 次接口调用</p>

<h2>1. 对账结论(能判对错的证据)</h2><div class="card">{recon_html}</div>
<h2>2. 检索接口 请求 / 返回(真值)</h2><div class="card">{api_html}</div>
<h2>3. 关键步骤截图</h2><div class="card">{shots_html or '<p class="muted">无截图</p>'}</div>
<h2>4. 流程视频(给人看)</h2><div class="card">{video_html}</div>
</div></body></html>"""
    out.write_text(doc, encoding="utf-8")
    return out
