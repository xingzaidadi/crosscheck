"""
UI 录制(record→page_model):录一次页面操作,蒸馏成语义 page_model 喂给 ui_actions 回放。
与"probe 自动发现写接口"对称 —— 让 UI 步骤也不用手写(借 dsh record→replay 思路)。

做法:往页面注入一段监听,把人的 input/change/click 记成带"最近标签 + 控件类型 + 值"的事件;
录完把原始事件蒸馏成 page_model(语义步骤)。蒸馏逻辑是纯函数 events_to_page_model,可离线测;
级联/网格这类点选被记成连续 click 步骤,回放端的 click(get_by_text)即可重放。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from core.workspace import kb_dir

# 注入页面的监听:记录交互事件到 window.__ccRec,带最近 form-item 标签 + 控件信息
RECORD_JS = r"""
() => {
  if (window.__ccRecInstalled) return;
  window.__ccRecInstalled = true;
  window.__ccRec = [];
  const labelOf = (el) => {
    const item = el.closest('[class*="form-item"],[class*="form_item"],.form-item');
    if (item) {
      const lab = item.querySelector('[class*="label"],label');
      if (lab) return (lab.innerText || '').replace(/[*＊]/g,'').trim();
    }
    return '';
  };
  const rec = (kind, el, value, text) => window.__ccRec.push({
    kind, tag: el.tagName.toLowerCase(), type: (el.getAttribute('type')||'').toLowerCase(),
    label: labelOf(el), value: value, text: (text||'').trim(), ts: Date.now()});
  document.addEventListener('change', (e) => {
    const el = e.target;
    if (el.tagName === 'SELECT') rec('change', el, el.options[el.selectedIndex] ? el.options[el.selectedIndex].text : el.value);
    else if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') rec('change', el, el.value);
  }, true);
  document.addEventListener('input', (e) => {
    const el = e.target;
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') rec('input', el, el.value);
  }, true);
  document.addEventListener('click', (e) => {
    const el = e.target;
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT') return; // 填类另记
    rec('click', el, '', el.innerText);
  }, true);
}
"""


def _is_date(ev: dict) -> bool:
    return ev.get("type") == "date" or any(h in (ev.get("label") or "") for h in ("日期", "date", "时间"))


def events_to_page_model(events: list[dict]) -> list[dict]:
    """原始交互事件 → 语义 page_model。纯函数(可离线测):
      input/change 文本框 → text(同标签连续输入去重取最后);日期框 → date
      select change      → select
      点选(级联/选项)   → click(按可见文本重放);点在空白/无文本的忽略
    """
    out: list[dict] = []
    for ev in events:
        kind, tag = ev.get("kind"), ev.get("tag")
        label, value, text = ev.get("label") or "", ev.get("value"), (ev.get("text") or "").strip()
        if kind in ("input", "change") and tag in ("input", "textarea"):
            if value in (None, ""):
                continue
            act = "date" if _is_date(ev) else "text"
            # 同一标签连续输入:更新最后一条,而非堆多条
            if out and out[-1].get("action") in ("text", "date") and out[-1].get("label") == label:
                out[-1]["value"] = value
                out[-1]["action"] = act
            else:
                out.append({"action": act, "label": label, "value": value})
        elif kind == "change" and tag == "select":
            if value in (None, ""):
                continue
            if out and out[-1].get("action") == "select" and out[-1].get("label") == label:
                out[-1]["value"] = value
            else:
                out.append({"action": "select", "label": label, "value": value})
        elif kind == "click":
            if not text or len(text) > 24:        # 只记短文本的语义点选(选项/按钮),忽略点空白/大块
                continue
            if out and out[-1].get("action") == "click" and out[-1].get("text") == text:
                continue                          # 去重连点
            out.append({"action": "click", "text": text})
    return out


def record(page_url: str, *, session_file: str | None = None, feature: str = "ui_flow",
           wait_ms: int = 60000) -> list[dict]:
    """有头浏览器录一次:注入监听 → 人操作 → 收事件 → 蒸馏 page_model。需交互式环境。"""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx_kwargs = {}
        if session_file and Path(session_file).exists():
            ctx_kwargs["storage_state"] = session_file
        ctx = browser.new_context(**ctx_kwargs)
        page = ctx.new_page()
        page.goto(page_url, wait_until="domcontentloaded")
        page.evaluate(RECORD_JS)
        import sys as _sys
        if _sys.stdin and _sys.stdin.isatty():
            print("【录制】在页面上完成一次操作,完成后回终端按回车…")
            try:
                input()
            except EOFError:
                page.wait_for_timeout(wait_ms)
        else:
            page.wait_for_timeout(wait_ms)
        events = page.evaluate("() => window.__ccRec || []")
        ctx.close(); browser.close()
    return events_to_page_model(events)


def save_page_model(feature: str, model: list[dict]) -> Path:
    path = kb_dir() / "page_model" / f"{feature}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        {"feature": feature, "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "steps": model},
        ensure_ascii=False, indent=2), encoding="utf-8")
    return path
