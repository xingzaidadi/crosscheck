"""Structured browser observation without application-specific selectors."""
from __future__ import annotations

from typing import Any


OBSERVE_JS = r"""
() => {
  const visible = (e) => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const labelFor = (e) => {
    const id = e.getAttribute('id');
    const explicit = id && document.querySelector(`label[for="${CSS.escape(id)}"]`);
    const wrapped = e.closest('label');
    return ((explicit && explicit.innerText) || (wrapped && wrapped.innerText) || '').trim();
  };
  // 穿透 shadow DOM 收集元素:原生 querySelectorAll 不进 shadow root,导致
  // qiankun/web-component 等微前端把业务控件渲染进 shadow DOM 后,观察器只看得到
  // 外壳而看不到真控件。此处递归下探每个 shadowRoot,用同一 selector 汇总(零业务、
  // 纯通用遍历),再按文档顺序去重返回。
  const queryDeep = (selector) => {
    const out = [];
    const seen = new Set();
    const walk = (root) => {
      let nodes;
      try { nodes = root.querySelectorAll(selector); } catch (e) { nodes = []; }
      nodes.forEach(n => { if (!seen.has(n)) { seen.add(n); out.push(n); } });
      const hosts = (root.querySelectorAll ? root.querySelectorAll('*') : []);
      hosts.forEach(h => { if (h.shadowRoot) walk(h.shadowRoot); });
    };
    walk(document);
    return out;
  };
  const controls = queryDeep('button,a,input,textarea,select,[role],[contenteditable="true"],summary,[tabindex]')
    .filter(visible).slice(0, 200).map((e, index) => ({
      index,
      tag: e.tagName.toLowerCase(),
      role: e.getAttribute('role') || '',
    text: (e.innerText || e.value || '').trim().slice(0, 120),
      label: (e.getAttribute('aria-label') || labelFor(e) || e.getAttribute('placeholder') || e.getAttribute('title') || '').trim(),
      name: e.getAttribute('name') || e.getAttribute('id') || '',
      type: e.getAttribute('type') || '',
      href: e.getAttribute('href') || '',
      testid: e.getAttribute('data-testid') || e.getAttribute('data-test') || '',
      disabled: !!e.disabled,
      readonly: !!e.readOnly
    }));
  const headings = queryDeep('h1,h2,h3,[role="heading"]')
    .filter(visible).slice(0, 50).map(e => (e.innerText || '').trim()).filter(Boolean);
  const rows = queryDeep('table tbody tr,[role="row"]')
    .filter(visible).slice(0, 20).map((e, index) => ({index, text: (e.innerText || '').trim().slice(0, 300)}));
  const fields = queryDeep('input,textarea,select')
    .filter(visible).slice(0, 100).map((e, index) => ({
      index, tag: e.tagName.toLowerCase(), type: e.getAttribute('type') || '',
      label: e.getAttribute('aria-label') || labelFor(e) || e.getAttribute('placeholder') || e.getAttribute('title') || '',
      name: e.getAttribute('name') || e.getAttribute('id') || '',
      type: e.getAttribute('type') || '',
      value: e.value || '', disabled: !!e.disabled, readonly: !!e.readOnly
    }));
  return {
    title: document.title,
    controls,
    headings,
    rows,
    fields,
    dialogs: queryDeep('[role="dialog"],dialog,.modal,.drawer').filter(visible).length,
    tables: queryDeep('table,[role="grid"]').length,
    editable_controls: queryDeep('input:not([type="hidden"]),textarea,select,[contenteditable="true"]')
      .filter(e => visible(e) && !e.disabled && !e.readOnly).length,
    navigation: queryDeep('nav,[role="navigation"],aside').filter(visible).slice(0, 10)
      .map(e => (e.innerText || '').trim().slice(0, 1000)).filter(Boolean),
    breadcrumbs: queryDeep('[aria-label*="breadcrumb" i],.breadcrumb,.breadcrumbs')
      .filter(visible).slice(0, 10).map(e => (e.innerText || '').trim()).filter(Boolean),
    frames: Array.from(document.querySelectorAll('iframe')).slice(0, 20).map((e, index) => ({
      index, name: e.name || '', title: e.title || '', src: e.src || ''
    })),
    shadow_hosts: queryDeep('*').filter(e => e.shadowRoot).slice(0, 20)
      .map((e, index) => ({index, tag: e.tagName.toLowerCase(), label: e.getAttribute('aria-label') || ''}))
  };
}
"""


def _deep_text(page) -> str:
    """跨 shadow DOM 汇总可见文本。body.inner_text 不进 shadow root,微前端把内容
    渲染进 shadow DOM 后会漏读;此处递归拼接各 shadowRoot 文本作为补充。"""
    js = r"""
    () => {
      const parts = [];
      const walk = (root) => {
        if (root.body) parts.push(root.body.innerText || '');
        const all = root.querySelectorAll ? root.querySelectorAll('*') : [];
        all.forEach(h => { if (h.shadowRoot) { parts.push(h.shadowRoot.textContent || ''); walk(h.shadowRoot); } });
      };
      walk(document);
      return parts.join('\n');
    }
    """
    try:
        return str(page.evaluate(js) or "")[:20000]
    except Exception:
        return ""


def wait_for_settle(page, *, timeout_ms: int = 12000, stable_ms: int = 600,
                    poll_ms: int = 300, loading_markers: tuple[str, ...] = ("加载中", "Loading", "loading")) -> bool:
    """等页面(含微前端子应用)挂载稳定后再观察。

    确定性、零业务:不认任何业务词,只做两件通用事——
      ① 轮询跨 shadow DOM 的可见文本,连续 stable_ms 内长度不变即判稳定;
      ② 文本里还残留通用"加载中/Loading"占位符时不算稳定(除非超时)。
    超时返回 False(调用方照常观察,不阻断),稳定返回 True。
    """
    import time as _time
    deadline = _time.monotonic() + timeout_ms / 1000.0
    last_len = -1
    stable_since = None
    while _time.monotonic() < deadline:
        text = _deep_text(page)
        cur_len = len(text.strip())
        loading = any(m in text for m in loading_markers)
        if cur_len > 0 and cur_len == last_len and not loading:
            if stable_since is None:
                stable_since = _time.monotonic()
            elif (_time.monotonic() - stable_since) * 1000 >= stable_ms:
                return True
        else:
            stable_since = None
        last_len = cur_len
        page.wait_for_timeout(poll_ms)
    return False


def observe(page) -> dict[str, Any]:
    snapshot = dict(page.evaluate(OBSERVE_JS) or {})
    snapshot["url"] = page.url
    try:
        body = page.locator("body").inner_text(timeout=3000)[:20000]
    except Exception:
        body = ""
    deep = _deep_text(page)
    # 合并:body.inner_text 的 light DOM 文本 + shadow DOM 补充文本,去重拼接。
    merged = body
    if deep and deep not in body:
        merged = (body + "\n" + deep)[:20000]
    snapshot["body_text"] = merged
    return snapshot
