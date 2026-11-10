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
                     actions=ui.get("actions"), extract=ui.get("extract"),
                     value_selectors=[a["selector"] for a in (ui.get("value_asserts") or [])],
                     visibility_asserts=ui.get("visibility_asserts"))
    except Exception as e:  # noqa: BLE001
        return CaseResult(case_id=spec.case_id, verdict=Verdict.ENV_ERROR,
                          details=[f"页面渲染/抓取异常: {e}"], duration_s=round(time.time() - t0, 3),
                          title=spec.title, kind=spec.kind, mode=spec.mode,
                          report={"did": did, "layers": [{"name": "渲染", "ok": False, "note": str(e)}], "evidence": {}})

    picked = prober.pick_search_call() or (prober.captures[-1] if prober.captures else None)
    api_resp = picked.response_json if picked else {}

    # 展示层(页面==接口)仅当配了 extract 才校验;纯可见性/纯值校验类 spec 不触发它
    if ui.get("extract"):
        ui_res = verify_display(prober.rendered_rows, api_resp, ui)
        layers.append(run_report.ui_layer(ui_res))
        if not ui_res.consistent:
            verdict = Verdict.FAIL

    # 页签/按钮计算:页面显示的数 == 库真值
    if ui.get("value_asserts"):
        from core.ui_value import check_values
        vok, vlayer = check_values(prober.value_reads, ui["value_asserts"], db)
        layers.append(vlayer)
        if not vok and verdict is Verdict.PASS:
            verdict = Verdict.FAIL

    # 元素可见性校验(按钮显示/隐藏类):命名控件是否在当前页面可见
    if prober.visibility_check:
        pok, player = prober.visibility_check
        layers.append(player)
        if not pok and verdict is Verdict.PASS:
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
    details += (ui_res.diffs if ui.get("extract") else []) + rec_diffs
    return CaseResult(case_id=spec.case_id, verdict=verdict, details=details,
                      duration_s=round(time.time() - t0, 3),
                      title=spec.title, kind=spec.kind, mode=spec.mode,
                      evidence=(shots[-1] if shots else ""), video=str(video),
                      report={"did": did, "layers": layers, "evidence": evidence})


def _render_marker(obj, marker: str):
    """把 page_model 里的 {{marker}}/{{AUTOTEST_标记值}} 占位换成本次 marker。"""
    if isinstance(obj, str):
        return obj.replace("{{marker}}", marker).replace("{{AUTOTEST_标记值}}", marker)
    if isinstance(obj, list):
        return [_render_marker(x, marker) for x in obj]
    if isinstance(obj, dict):
        return {k: _render_marker(v, marker) for k, v in obj.items()}
    return obj


def run_ui_write_spec(spec, db: DbClient | None = None, run_dir: Path | None = None,
                      no_cleanup: bool = False) -> CaseResult:
    """UI 写入:开页面 → 语义回放 page_model(含复杂控件+自愈)→ 提交 → 验库 → 清理 → 富报告。
    让 UI 回放/录制/自愈接进执行主链,真跑一条 UI 写入用例(页面操作这层从单测就位变成能跑)。"""
    from core.marker import make_marker
    from core.verifier import Verifier
    from core.cleaner import Cleaner
    from core.engine import spec_to_testcase, _db_assert_layer
    from core.interfaces import ActionResult
    from core.workspace import workspace_root

    t0 = time.time()
    ui = spec.ui or {}
    page_url = ui.get("page_url") or ""
    if page_url and not page_url.startswith("http"):
        page_url = spec.base_url.rstrip("/") + "/" + page_url.lstrip("/")
    marker = make_marker(spec.case_id)
    model = _render_marker(ui.get("page_model") or [], marker)

    rundir = (run_dir / "cases" / spec.case_id) if run_dir else (artifacts_dir() / f"uiw_{spec.case_id}_{int(time.time())}")
    prober = Prober(url_pattern=ui.get("url_pattern", ""), session_file=spec.session,
                    headless=not bool(ui.get("headed")), launch_mode="isolated",
                    artifacts_dir=str(rundir), video_dir=str(rundir) if ui.get("video", True) else None)

    case = spec_to_testcase(spec)
    cleaner = Cleaner(db, workspace_root() / ".cleanup_registry.json") if db is not None else None
    if cleaner and not no_cleanup:
        cleaner.register(case, marker)

    did = [f"打开页面 {page_url}", f"语义回放 {len(model)} 步(唯一标记 {marker})", "提交并验库"]
    verdict, layers, details = Verdict.PASS, [], []
    try:
        prober.probe(page_url, wait_ms=ui.get("wait_ms", 4000), replay_actions=model,
                     field_asserts=_render_marker(ui.get("field_asserts") or [], marker) or None,
                     visibility_asserts=_render_marker(ui.get("visibility_asserts") or [], marker) or None)
    except Exception as e:  # noqa: BLE001
        if cleaner and not no_cleanup:
            cleaner.cleanup(marker)
        return CaseResult(case_id=spec.case_id, verdict=Verdict.ENV_ERROR,
                          details=[f"页面渲染/回放异常: {e}"], duration_s=round(time.time() - t0, 3),
                          title=spec.title, kind=spec.kind, mode=spec.mode,
                          report={"did": did, "layers": [{"name": "渲染", "ok": False, "note": str(e)}], "evidence": {}})

    rr = prober.replay_results
    steps_ok = all(r["ok"] for r in rr) if rr else False
    layers.append({"name": "UI 操作回放(含自愈)", "ok": steps_ok,
                   "cols": ["动作", "目标", "结果", "自愈策略"],
                   "rows": [[r["action"], r["target"], "✓" if r["ok"] else f"✗ {r.get('error','')}",
                             r.get("heal", "")] for r in rr]})
    if not steps_ok:
        verdict = Verdict.FAIL
        details += [f"回放失败: {r['target']} {r.get('error','')}" for r in rr if not r["ok"]]

    # 前端校验类:填非法值后页面应给出预期校验提示
    if ui.get("expect_validation"):
        from core.ui_validation import check_validation
        vok, vlayer = check_validation(prober.validation_errors, ui["expect_validation"])
        layers.append(vlayer)
        if not vok and verdict is Verdict.PASS:
            verdict = Verdict.FAIL

    # 字段联动/只读校验(前端行为,只能在页面上验)
    if prober.field_check:
        fok, flayer = prober.field_check
        layers.append(flayer)
        if not fok:
            if verdict is Verdict.PASS:
                verdict = Verdict.FAIL
            details += [f"字段校验不一致: {r[0]}" for r in flayer.get("rows", []) if r[-1] == "✗"]

    # 元素可见性校验(按钮显示/隐藏类)
    if prober.visibility_check:
        pok, player = prober.visibility_check
        layers.append(player)
        if not pok:
            if verdict is Verdict.PASS:
                verdict = Verdict.FAIL
            details += [f"可见性不符: {r[0]}" for r in player.get("rows", []) if r[-1] == "✗"]

    write = prober.pick_write_call()
    if write is not None:
        ok = (write.status or 0) < 400
        layers.append({"name": "提交接口", "ok": ok,
                       "actual": f"{write.method} {write.url} · HTTP {write.status}", "note": str(write.response_json)[:160]})

    if db is not None and case.expected.db:
        vverdict, vdetails = Verifier(db).verify(case, marker, ActionResult(ok=True), {"marker": marker})
        details += vdetails
        layers.append(_db_assert_layer(case, db, marker, {"marker": marker}))
        if vverdict is not Verdict.PASS and verdict is Verdict.PASS:
            verdict = vverdict

    cleanup_ok = True if no_cleanup else (cleaner.cleanup(marker) if cleaner else True)

    shots = [s["path"] for s in prober.screenshots]
    video = prober.video_path or ""
    evidence = {"screenshots": _relpaths(shots, run_dir) if run_dir else shots}
    if video:
        evidence["video"] = (_relpaths([video], run_dir)[0] if run_dir else str(video))
    layers.append({"name": "数据清理", "ok": cleanup_ok,
                   "actual": (f"已跳过清理,数据保留(标记 {marker})" if no_cleanup
                              else ("已销账" if cleanup_ok else "部分未清,标 cleanup_pending"))})

    fid, audit, verdict = _score_and_audit_ui(spec, layers, write, bool(shots), bool(video), run_dir, verdict, details, marker)

    return CaseResult(case_id=spec.case_id, verdict=verdict, details=details or ["UI 回放+验库通过"],
                      cleanup_ok=cleanup_ok, duration_s=round(time.time() - t0, 3),
                      title=spec.title, kind=spec.kind, mode=spec.mode,
                      evidence=(shots[-1] if shots else ""), video=str(video),
                      act_via=audit.get("actual_act_via", ""), ui_triggered=audit.get("ui_triggered", False),
                      fidelity=fid, audit=audit,
                      report={"did": did, "layers": layers, "evidence": evidence,
                              "fidelity": fid, "audit": audit})


def _score_and_audit_ui(spec, layers, write, has_shots, has_video, run_dir, verdict, details, marker="") -> tuple[dict, dict, object]:
    """UI 执行器的走单对账打分 + 审计。默认加法不改 verdict;门禁开启时对"声明走单却没走"降级。"""
    from core import fidelity
    from core.engine import _layer_ok, _dump_audit
    from core.interfaces import Verdict
    expect_ui = (getattr(spec, "act_via", "auto") != "api")
    ui_triggered = write is not None
    api_ok = _layer_ok(layers, "提交接口")
    db_ok = _layer_ok(layers, "库断言")
    evid_ok = has_shots and has_video
    # 纯前端校验类(expect_validation)本就不落库 → 不要求库腿;其余 UI 写入要求接口+库两腿
    require_db = not bool((spec.ui or {}).get("expect_validation"))
    # 三源同单做实:标记须同时在【页面驱动】【写请求体】【库】三处(不再用代理)
    if db_ok is None and not require_db:
        consistent, src = None, {}
    else:
        req_body = getattr(write, "request_body", None) if write is not None else None
        consistent, src = fidelity.tri_source_consistent(marker, req_body, ui_triggered, bool(db_ok))
    dims = fidelity.build_dims(expect_ui=expect_ui, ui_triggered=ui_triggered,
                               api_ok=api_ok, db_ok=db_ok, consistent=consistent, evidence_ok=evid_ok,
                               require_api=True, require_db=require_db)
    w, bands, opts = fidelity.load_scoring()
    fid = fidelity.score_case(dims, weights=w, grade_bands=bands).as_dict()
    layers.append(fidelity.score_layer(fid, int(opts.get("pass_score", 60))))
    gated = False
    if expect_ui and not ui_triggered and fidelity.is_strict(opts) and verdict is Verdict.PASS:
        verdict = Verdict.FAIL          # 门禁:走单类却没录到页面触发的写调用
        details.insert(0, "走单对账门禁:UI 回放未录到页面触发的写调用,判不达标")
        gated = True
    audit = {
        "declared_act_via": getattr(spec, "act_via", "auto"),
        "actual_act_via": "ui",
        "ui_triggered": ui_triggered,
        "ui_triggered_calls": ([{"method": write.method, "url": write.url, "status": write.status}]
                               if write is not None else []),
        "strict_gate": gated,
        "consistency_sources": src,   # 三源同单做实:标记在 页面/写请求体/库 各源的命中详情
        "note": ("页面驱动了被测写动作,录到该写调用" if ui_triggered
                 else "UI 回放未录到写调用(页面可能未真正提交/被前端拦)"),
        "fidelity": fid,
    }
    _dump_audit(spec.case_id, run_dir, audit)
    return fid, audit, verdict
