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
  const controls = Array.from(document.querySelectorAll('button,a,input,textarea,select,[role],[contenteditable="true"],summary,[tabindex]'))
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
  const headings = Array.from(document.querySelectorAll('h1,h2,h3,[role="heading"]'))
    .filter(visible).slice(0, 50).map(e => (e.innerText || '').trim()).filter(Boolean);
  const rows = Array.from(document.querySelectorAll('table tbody tr,[role="row"]'))
    .filter(visible).slice(0, 20).map((e, index) => ({index, text: (e.innerText || '').trim().slice(0, 300)}));
  const fields = Array.from(document.querySelectorAll('input,textarea,select'))
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
    dialogs: Array.from(document.querySelectorAll('[role="dialog"],dialog,.modal,.drawer')).filter(visible).length,
    tables: document.querySelectorAll('table,[role="grid"]').length,
    editable_controls: Array.from(document.querySelectorAll('input:not([type="hidden"]),textarea,select,[contenteditable="true"]'))
      .filter(e => visible(e) && !e.disabled && !e.readOnly).length,
    navigation: Array.from(document.querySelectorAll('nav,[role="navigation"],aside')).filter(visible).slice(0, 10)
      .map(e => (e.innerText || '').trim().slice(0, 1000)).filter(Boolean),
    breadcrumbs: Array.from(document.querySelectorAll('[aria-label*="breadcrumb" i],.breadcrumb,.breadcrumbs'))
      .filter(visible).slice(0, 10).map(e => (e.innerText || '').trim()).filter(Boolean),
    frames: Array.from(document.querySelectorAll('iframe')).slice(0, 20).map((e, index) => ({
      index, name: e.name || '', title: e.title || '', src: e.src || ''
    })),
    shadow_hosts: Array.from(document.querySelectorAll('*')).filter(e => e.shadowRoot).slice(0, 20)
      .map((e, index) => ({index, tag: e.tagName.toLowerCase(), label: e.getAttribute('aria-label') || ''}))
  };
}
"""


def observe(page) -> dict[str, Any]:
    snapshot = dict(page.evaluate(OBSERVE_JS) or {})
    snapshot["url"] = page.url
    try:
        snapshot["body_text"] = page.locator("body").inner_text(timeout=3000)[:20000]
    except Exception:
        snapshot["body_text"] = ""
    return snapshot
