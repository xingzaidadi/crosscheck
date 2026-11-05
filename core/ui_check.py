"""
三层一致性校验(库 ↔ 接口 ↔ 页面渲染)的编排。

一条 UI 用例:
  1) 用 Prober 渲染页面(复用登录态)→ 抓到页面触发的接口 + 按规则抽取 DOM 实际显示的行/字段 + 录像/截图;
  2) 页面↔接口:verify_display 比"页面显示" vs "接口返回";
  3) 接口↔库:Reconciler 比"接口返回" vs "数据库"(有 feature 映射时);
三层都对上才 PASS。证据(截图/录像/接口数据)落在本次运行目录。执行期确定性,不碰 LLM。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from core import run_report
from core.interfaces import CaseResult, Verdict
from core.prober import Prober
from core.reconciler import Reconciler
from core.ui_verifier import verify_display
from core.workspace import artifacts_dir, kb_dir
from db.client import DbClient


def _describe_actions(actions) -> list[str]:
    out = []
    for a in actions or []:
        if not isinstance(a, dict) or not a:
            continue
        k = next(iter(a)); spec = a[k]
        if k == "click":
            out.append(f"点击『{spec.get('selector')}』")
        elif k == "select":
            out.append(f"选择『{spec.get('selector')}』= {spec.get('value') or spec.get('label')}")
        elif k == "fill":
            out.append(f"填写『{spec.get('selector')}』")
        elif k == "wait_ms":
            pass
    return out


def _relpaths(paths, run_dir: Path) -> list[str]:
    out = []
    for p in paths:
        try:
            out.append(str(Path(p).resolve().relative_to(run_dir.resolve())).replace("\\", "/"))
        except Exception:  # noqa: BLE001
            out.append(str(p))
    return out


def run_ui_spec(spec, db: DbClient | None = None, run_dir: Path | None = None) -> CaseResult:
    t0 = time.time()
    ui = spec.ui or {}
    page_url = ui.get("page_url") or ""
    if page_url and not page_url.startswith("http"):
        page_url = spec.base_url.rstrip("/") + "/" + page_url.lstrip("/")

    rundir = (run_dir / "cases" / spec.case_id) if run_dir else (artifacts_dir() / f"ui_{spec.case_id}_{int(time.time())}")
    headed = bool(ui.get("headed"))
    want_video = ui.get("video", True)
    prober = Prober(url_pattern=ui.get("url_pattern", ""), session_file=spec.session,
                    headless=not headed, launch_mode="isolated", artifacts_dir=str(rundir),
                    video_dir=str(rundir) if want_video else None)

    did = [f"打开页面 {page_url}"]
    did += _describe_actions(ui.get("actions"))
    did.append(f"抓接口 {ui.get('url_pattern') or '(全部 xhr/fetch)'}")
    did.append("抽取页面实际显示的" + ("字段" if "fields" in (ui.get("extract") or {}) else "行"))

    verdict, layers = Verdict.PASS, []
    try:
        prober.probe(page_url, wait_ms=ui.get("wait_ms", 5000),
                     actions=ui.get("actions"), extract=ui.get("extract"))
    except Exception as e:  # noqa: BLE001
        return CaseResult(case_id=spec.case_id, verdict=Verdict.ENV_ERROR,
                          details=[f"页面渲染/抓取异常: {e}"], duration_s=round(time.time() - t0, 3),
                          title=spec.title, kind=spec.kind, mode=spec.mode,
                          report={"did": did, "layers": [{"name": "渲染", "ok": False, "note": str(e)}], "evidence": {}})

    picked = prober.pick_search_call() or (prober.captures[-1] if prober.captures else None)
    api_resp = picked.response_json if picked else {}

    ui_res = verify_display(prober.rendered_rows, api_resp, ui)
    layers.append(run_report.ui_layer(ui_res))
    if not ui_res.consistent:
        verdict = Verdict.FAIL
    if picked is None:
        verdict = Verdict.ENV_ERROR
        layers.append({"name": "抓接口", "ok": False, "note": "没抓到页面触发的接口(检查 url_pattern / 是否需要操作)"})

    rec_diffs: list[str] = []
    feature = spec.feature
    mapping_path = kb_dir() / "query_mapping" / f"{feature}.json" if feature else None
    if db is not None and mapping_path and mapping_path.exists() and picked is not None:
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        rec = Reconciler(db, mapping).reconcile(picked.request_body or {}, api_resp)
        layers.append(run_report.reconcile_layer(rec, mapping))
        rec_diffs = rec.count_diffs + rec.field_diffs
        if not rec.consistent and verdict is Verdict.PASS:
            verdict = Verdict.FAIL

    shots = [s["path"] for s in prober.screenshots]
    video = prober.video_path or ""
    evidence = {"screenshots": _relpaths(shots, run_dir) if run_dir else shots}
    if video:
        evidence["video"] = (_relpaths([video], run_dir)[0] if run_dir else str(video))

    # 存接口原始数据到用例目录
    if picked is not None:
        try:
            (rundir / "api_response.json").write_text(
                json.dumps(api_resp, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    details = [f"[{ly['name']}] {'一致' if ly.get('ok') else '不一致'}" for ly in layers]
    details += ui_res.diffs + rec_diffs
    return CaseResult(case_id=spec.case_id, verdict=verdict, details=details,
                      duration_s=round(time.time() - t0, 3),
                      title=spec.title, kind=spec.kind, mode=spec.mode,
                      evidence=(shots[-1] if shots else ""), video=str(video),
                      report={"did": did, "layers": layers, "evidence": evidence})
