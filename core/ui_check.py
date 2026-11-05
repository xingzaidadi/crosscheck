"""
三层一致性校验(库 ↔ 接口 ↔ 页面渲染)的编排。

一条 UI 用例:
  1) 用 Prober 渲染页面(复用登录态)→ 抓到页面触发的接口 + 按规则抽取 DOM 实际显示的行 + 截图;
  2) 页面↔接口:verify_display 比"页面显示的行" vs "接口返回的行";
  3) 接口↔库:Reconciler 比"接口返回" vs "数据库"(有 feature 映射时);
三层都对上才 PASS。证据 = 页面截图。执行期确定性,不碰 LLM。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from core.interfaces import CaseResult, Verdict
from core.prober import Prober
from core.reconciler import Reconciler
from core.ui_verifier import verify_display
from core.workspace import artifacts_dir, kb_dir
from db.client import DbClient


def run_ui_spec(spec, db: DbClient | None = None) -> CaseResult:
    t0 = time.time()
    ui = spec.ui or {}
    page_url = ui.get("page_url") or ""
    if page_url and not page_url.startswith("http"):
        page_url = spec.base_url.rstrip("/") + "/" + page_url.lstrip("/")

    rundir = artifacts_dir() / f"ui_{spec.case_id}_{int(time.time())}"
    headed = bool(ui.get("headed"))          # 有头=弹可见窗口(给人看);默认无头
    prober = Prober(url_pattern=ui.get("url_pattern", ""), session_file=spec.session,
                    headless=not headed, launch_mode="isolated", artifacts_dir=str(rundir))
    details: list[str] = []
    verdict = Verdict.PASS
    try:
        prober.probe(page_url, wait_ms=ui.get("wait_ms", 5000),
                     actions=ui.get("actions"), extract=ui.get("extract"))
    except Exception as e:  # noqa: BLE001
        return CaseResult(case_id=spec.case_id, verdict=Verdict.ENV_ERROR,
                          details=[f"页面渲染/抓取异常: {e}"], duration_s=round(time.time() - t0, 3),
                          title=spec.title, kind=spec.kind, mode=spec.mode)

    picked = prober.pick_search_call()
    if picked is None and prober.captures:
        picked = prober.captures[-1]
    if picked is None:
        verdict = Verdict.ENV_ERROR
        details.append("没抓到页面触发的接口(检查 url_pattern / 页面是否需要操作)")
    api_resp = picked.response_json if picked else {}

    # 2) 页面 ↔ 接口
    ui_res = verify_display(prober.rendered_rows, api_resp, ui)
    details += ui_res.render().splitlines()
    if not ui_res.consistent:
        verdict = Verdict.FAIL

    # 3) 接口 ↔ 库(有映射才做)
    feature = spec.feature
    mapping_path = kb_dir() / "query_mapping" / f"{feature}.json" if feature else None
    if db is not None and mapping_path and mapping_path.exists() and picked is not None:
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        rec = Reconciler(db, mapping).reconcile(picked.request_body or {}, api_resp)
        details += rec.render().splitlines()
        if not rec.consistent and verdict is Verdict.PASS:
            verdict = Verdict.FAIL
    else:
        details.append("(未配 feature 映射,跳过接口↔库对账,仅做页面↔接口)")

    shot = next((s["path"] for s in reversed(prober.screenshots) if s["name"] == "rendered"),
                prober.screenshots[-1]["path"] if prober.screenshots else "")
    return CaseResult(case_id=spec.case_id, verdict=verdict, details=details,
                      duration_s=round(time.time() - t0, 3),
                      title=spec.title, kind=spec.kind, mode=spec.mode, evidence=shot)
