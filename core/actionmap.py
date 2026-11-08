"""动作报文自发现(通用、零业务):很多写/动作接口盲构报文必 500——只有被真实触发过才知道
正确报文。actionmap 复用 prober 录放:驱动一次该动作的 UI 触发,抓到那次写调用,存成可复用
的"动作桩"(endpoint + 报文模板)。之后建模/就绪门禁就知道这个动作"有真实报文、可执行"。

不认识任何业务:动作怎么触发(页面 + 点哪个)由 workspace 的动作清单给,core 只负责录、挑、存。

可测纯函数:normalize_stub / stub_to_route / endpoints_from_stubs
活部件(可注入 probe_fn):capture_action / build_actionmap
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from core.readiness import norm_endpoint


def _default_probe(page_url: str, **kw):
    """活录:开浏览器带登录态,驱动 actions/replay_actions,全程抓接口,返回 Prober 实例。"""
    from core.prober import Prober
    pr = Prober(url_pattern=kw.get("url_pattern", ""), session_file=kw.get("session_file"),
                headless=kw.get("headless", True))
    pr.probe(page_url, actions=kw.get("actions"), replay_actions=kw.get("replay_actions"),
             wait_ms=kw.get("wait_ms", 3000))
    return pr


def capture_action(page_url: str, *, probe_fn: Callable | None = None, **kw) -> dict | None:
    """驱动一次动作触发,挑出那次写调用,转成动作桩 {endpoint:{method,url}, template_body}。
    抓不到写调用返回 None(该动作未真正触发,或响应非写)。"""
    from core.prober import write_stub_from_capture
    probe_fn = probe_fn or _default_probe
    pr = probe_fn(page_url, **kw)
    cap = pr.pick_write_call()
    if cap is None:
        return None
    return write_stub_from_capture(cap)


def normalize_stub(stub: dict, *, marker_fields: list[str] | None = None,
                   drop_fields: list[str] | None = None) -> dict:
    """把抓到的动作桩规整成可复用模板:去服务端自增字段(drop),标记字段注 {{marker}} 占位。
    纯字典操作,零业务;实际建模时 modeler 会在此基础上再拼。"""
    body = dict(stub.get("template_body") or {}) if isinstance(stub.get("template_body"), dict) else stub.get("template_body")
    if isinstance(body, dict):
        for d in (drop_fields or []):
            body.pop(d, None)
        for mf in (marker_fields or []):
            if mf in body:
                body[mf] = "{{marker}}"
    return {"endpoint": dict(stub.get("endpoint") or {}), "template_body": body}


def stub_to_route(stub: dict, *, marker_fields: list[str] | None = None,
                  table: str = "", parent_key: str = "", parent_marker_col: str = "",
                  assert_status: dict | None = None, expect_rejected: bool = False) -> dict:
    """动作桩 → case_routes 风格的 write 路由片段(endpoint + body_set 标记 + 断言脚手架)。
    把"抓到的报文"直接变成"可执行规格",桥接 capture→执行。零业务。"""
    ep = dict(stub.get("endpoint") or {})
    w: dict[str, Any] = {"endpoint": ep}
    body = stub.get("template_body")
    if isinstance(body, dict):
        w["inline_body"] = body       # 内联报文(modeler 可直接用,无需外部 template 文件)
    if marker_fields:
        w["marker_fields"] = list(marker_fields)
    if table:
        w["table"] = table
        if parent_key:
            w["parent_key"] = parent_key
        if parent_marker_col:
            w["parent_marker_col"] = parent_marker_col
        if assert_status:
            w["assert_status"] = assert_status
    if expect_rejected:
        w["response"] = {"rejected": True}
        w["assert_row_count"] = 0
    return {"mode": "write", "write": w}


def save_action_stub(site: str, action_key: str, stub: dict) -> Path:
    from core.workspace import kb_dir
    out = kb_dir() / "action_stubs" / site / f"{action_key}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(stub, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def load_action_stub(site: str, action_key: str) -> dict | None:
    from core.workspace import kb_dir
    p = kb_dir() / "action_stubs" / site / f"{action_key}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def endpoints_from_stubs(site: str) -> set[str]:
    """已抓到报文的动作端点集(规整 path)——喂 readiness.reachable:有桩=可复现=可执行。"""
    from core.workspace import kb_dir
    d = kb_dir() / "action_stubs" / site
    eps: set[str] = set()
    if not d.exists():
        return eps
    for f in d.glob("*.json"):
        try:
            stub = json.loads(f.read_text(encoding="utf-8"))
            url = (stub.get("endpoint") or {}).get("url")
            if url:
                eps.add(norm_endpoint(url))
        except Exception:  # noqa: BLE001
            pass
    return eps


def build_actionmap(site: str, actions: list[dict], *, probe_fn: Callable | None = None) -> dict:
    """批量录动作。actions: [{key, page_url, actions?/replay_actions?, before?, session_file?, ...}]。
    每个独立容错;抓到就存桩。返回 {key: {ok, source_path|missing}}。"""
    out = {}
    for a in actions:
        key = a.get("key") or ""
        try:
            stub = capture_action(a["page_url"], probe_fn=probe_fn,
                                  actions=a.get("actions"), replay_actions=a.get("replay_actions"),
                                  session_file=a.get("session_file"), url_pattern=a.get("url_pattern", ""),
                                  wait_ms=a.get("wait_ms", 3000), headless=a.get("headless", True))
            if stub is None:
                out[key] = {"ok": False, "missing": "未抓到写调用(动作未触发/响应非写)"}
            else:
                p = save_action_stub(site, key, stub)
                out[key] = {"ok": True, "source_path": str(p), "endpoint": stub.get("endpoint")}
        except Exception as e:  # noqa: BLE001
            out[key] = {"ok": False, "missing": f"录制异常: {str(e)[:100]}"}
    return out
