"""
写入类执行编排(ExecSpec 驱动):
  登记 → 造前置状态(data_prep)→ 前置快照 → 主写动作(+可选一键审批)
       → 校验(响应+库)→ diff 安全网 → 清理(按 marker 反删)。
控制流写死,执行期纯确定性,不碰 LLM。复用 ApiAdapter/Verifier/SnapshotGuard/Cleaner。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from adapters.api_adapter import ApiAdapter
from core.cleaner import Cleaner
from core.interfaces import CaseResult, DbAssertion, Expected, TestCase, Verdict
from core.marker import make_marker
from core.snapshot import SnapshotGuard
from core.verifier import Verifier, _dig, _MISSING
from db.client import DbClient


def _resolve_business_key(approve: dict, action, db: DbClient, marker: str):
    """审批前拿 businessKey:优先从提交响应取(response 路径),否则按 marker 查库。"""
    bkf = approve.get("business_key_from") or {}
    if bkf.get("response"):
        v = _dig(action.api_body, bkf["response"])
        return None if v is _MISSING else v
    q = bkf.get("db")
    if q:
        where = (q["where"].replace("{{AUTOTEST_标记值}}", marker).replace("{{marker}}", marker))
        rows = db.query(f"SELECT {q['column']} AS bk FROM {q['table']} WHERE {where}")
        return rows[0]["bk"] if rows else None
    return None


def spec_to_testcase(spec) -> TestCase:
    """ExecSpec → 内核契约 TestCase(断言/allowed_tables 落 Expected,写执行要素挂 raw)。"""
    db_asserts = [
        DbAssertion(db=a.get("db", ""), table=a["table"], where=a["where"],
                    row_count=a.get("row_count"), fields=a.get("fields") or {})
        for a in (spec.assertions.get("db") or [])
    ]
    expected = Expected(
        page=spec.assertions.get("page") or [],
        db=db_asserts, allowed_tables=spec.allowed_tables)
    raw = {
        "request": spec.request,
        "marker_field": spec.marker_field,
        "response_assert": spec.assertions.get("response") or {},
        "cleanup_targets": spec.cleanup,
        "approve": spec.approve,
        "data_prep": spec.data_prep,
        "verify_poll": spec.verify_poll,
        "event_asserts": spec.assertions.get("events") or [],
    }
    return TestCase(case_id=spec.case_id, feature=spec.feature or spec.case_id,
                    account_ref="", data_prep=None, steps=[], expected=expected, raw=raw)


def _db_assert_layer(case: TestCase, db: DbClient, marker: str, vars: dict | None = None) -> dict:
    """验库层:按断言逐表逐字段列『预期 vs 实际』,给富报告。"""
    cols = ["表", "where", "预期行数", "实际行数", "字段", "预期", "实际", "一致"]
    rows, tables, ok_all = [], [], True
    for a in case.expected.db:
        where = a.where.replace("{{AUTOTEST_标记值}}", marker)
        for k, v in (vars or {}).items():
            where = where.replace("{{" + k + "}}", str(v))
        tables.append(a.table)
        try:
            got_rows = db.query(f"SELECT * FROM {a.table} WHERE {where}")
        except Exception as e:  # noqa: BLE001
            ok_all = False
            rows.append([a.table, where, a.row_count, f"查询失败:{e}", "—", "—", "—", "✗"])
            continue
        cnt_ok = a.row_count is None or len(got_rows) == a.row_count
        if not cnt_ok:
            ok_all = False
        if a.fields:
            for col, exp in a.fields.items():
                got = got_rows[0].get(col) if got_rows else None
                f_ok = cnt_ok and bool(got_rows) and str(got) == str(exp)
                if not f_ok:
                    ok_all = False
                rows.append([a.table, where, a.row_count, len(got_rows), col, exp, got, "✓" if f_ok else "✗"])
        else:
            rows.append([a.table, where, a.row_count, len(got_rows), "—", "—", "—", "✓" if cnt_ok else "✗"])
    return {"name": "库断言(提交/审批后落库)", "ok": ok_all,
            "expected": "单据按标记落库,行数与状态字段符合预期",
            "tables": sorted(set(tables)), "cols": cols, "rows": rows}


def run_write_spec(spec, db: DbClient, *, base_url: str = "", session_file: str = "",
                   registry_path=".", run_dir=None) -> CaseResult:
    """执行一条写入类 ExecSpec,返回 CaseResult(含富报告层)。db 需带写连接(清理用)。"""
    t0 = time.time()
    case = spec_to_testcase(spec)
    marker = make_marker(spec.case_id)
    adapter = ApiAdapter(base_url=base_url or spec.base_url, session_file=session_file or spec.session)
    guard = SnapshotGuard(db, full_scan=getattr(spec, "diff_full_scan", True))
    verifier = Verifier(db)
    cleaner = Cleaner(db, registry_path)
    req = case.raw.get("request") or {}

    verdict, details = Verdict.PASS, []
    did, layers, bk, action, ar = [], [], None, None, None
    cleaner.register(case, marker)
    try:
        adapter.setup(case)

        # 前置造数:逐个发请求造出所需状态单;capture 把返回里的值(如单号)抓进 vars,
        # 供主动作/审批/断言用 {{var}} 引用(状态守卫/流转/编辑类用例的前提)。
        vars = {"marker": marker}
        for prep in (case.raw.get("data_prep") or []):
            r = adapter.call(prep, vars)
            did.append(f"造前置状态 {prep.get('method')} {prep.get('url')}")
            if not r.ok:
                details.append(f"data_prep 失败: {r.error or r.api_status}")
            for var, path in (prep.get("capture") or {}).items():
                val = _dig(r.api_body, path)
                if val is _MISSING:
                    details.append(f"data_prep 未抓到 {var}(路径 {path})")
                else:
                    vars[var] = val

        guard.snapshot_before(case.expected)
        action = adapter.perform(case, marker, vars)
        did.append(f"执行写动作 {req.get('method')} {req.get('url')}(唯一标记 {marker})")
        code = _dig(action.api_body, "code")
        doc_no = _dig(action.api_body, "data.demandRequestCode")
        layers.append({
            "name": "提交接口", "ok": bool(action.ok),
            "expected": "HTTP<400 且业务 code=0,生成单据",
            "actual": f"HTTP {action.api_status} · code={'—' if code is _MISSING else code}"
                      f" · 单号={'—' if doc_no is _MISSING else doc_no}",
            "note": str(action.api_body)[:300]})

        approve = case.raw.get("approve") or {}
        if approve:
            bk = _resolve_business_key(approve, action, db, marker)
            avars = dict(vars)
            if bk is not None:
                avars["businessKey"] = bk
            elif approve.get("business_key_from"):
                details.append("一键审批:未取到 businessKey(检查 business_key_from)")
            did.append(f"BPM 审批 {approve.get('method')} {approve.get('url')}(businessKey={bk})")
            # 审批走独立鉴权 session(BPM 主机与业务站不同域);没配则复用主 adapter
            appr_session = approve.get("session")
            if appr_session:
                appr = ApiAdapter(base_url=approve.get("base_url", ""), session_file=appr_session)
                try:
                    appr.setup()
                    ar = appr.call(approve, avars)
                finally:
                    appr.teardown()
            else:
                ar = adapter.call(approve, avars)
            appr_ok = ar.ok
            appr_notes = []
            if not ar.ok:
                appr_ok = False
                details.append(f"一键审批失败: {ar.error or ar.api_status}")
            for path, val in ((approve.get("expect") or {}).get("body") or {}).items():
                got = _dig(ar.api_body, path)
                if _MISSING is got or str(got) != str(val):
                    appr_ok = False
                    details.append(f"审批响应 {path}: 预期 {val!r} vs 实际 {got!r}")
                    appr_notes.append(f"{path}: 预期 {val} vs 实际 {got}")
            layers.append({
                "name": "BPM 审批", "ok": appr_ok,
                "expected": "审批接口返回 " + str((approve.get("expect") or {}).get("body") or "HTTP<400"),
                "actual": f"HTTP {ar.api_status} · {str(ar.api_body)[:160]}",
                "note": "; ".join(appr_notes)})

        verdict, vdetails = verifier.verify(case, marker, action, vars)
        details += vdetails

        # 异步/事件校验:等事件表/外部通知在时限内按标记落地(事件消费/异步导出/飞书/MQ)
        ev_asserts = case.raw.get("event_asserts") or []
        if ev_asserts:
            from core.events import check_events
            eok, edetails, elayers = check_events(
                ev_asserts, marker=marker, vars=vars, db=db,
                base_url=adapter.base_url, session_file=spec.session)
            details += edetails
            layers += elayers
            if not eok and verdict is Verdict.PASS:
                verdict = Verdict.FAIL

        dverdict, ddetails = guard.snapshot_after(case.expected, marker)
        if dverdict is not Verdict.PASS:
            details += ddetails
            if verdict is Verdict.PASS:
                verdict = dverdict

        if case.expected.db:
            layers.append(_db_assert_layer(case, db, marker, vars))
    except Exception as e:  # noqa: BLE001
        verdict, details = Verdict.ENV_ERROR, [f"执行异常: {e}"]
        layers.append({"name": "执行异常", "ok": False, "note": str(e)})
    finally:
        adapter.teardown()

    cleanup_ok = cleaner.cleanup(marker)
    n_child = sum(1 for t in (case.raw.get("cleanup_targets") or []) if t.get("parent"))
    did.append(f"清理:按标记删主表 + 按父单号删 {n_child} 张子表")
    layers.append({
        "name": "数据清理", "ok": cleanup_ok,
        "expected": "本次造数全部反删,registry 销账",
        "actual": "已销账(全删成功)" if cleanup_ok else "部分未清,标 cleanup_pending",
        "note": f"主表按标记列反删;{n_child} 张子表按父单号(父表标记列命中)反查删"})

    evidence = {}
    if run_dir is not None:
        try:
            case_dir = Path(run_dir) / "cases" / spec.case_id
            case_dir.mkdir(parents=True, exist_ok=True)
            rendered = adapter._render(req.get("body"), {"marker": marker})
            (case_dir / "api_request.json").write_text(
                json.dumps({"method": req.get("method"), "url": req.get("url"), "body": rendered},
                           ensure_ascii=False, indent=2), encoding="utf-8")
            (case_dir / "api_response.json").write_text(
                json.dumps(action.api_body if action else None, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8")
            data_ev = ["cases/" + spec.case_id + "/api_request.json",
                       "cases/" + spec.case_id + "/api_response.json"]
            if ar is not None:
                (case_dir / "approve_response.json").write_text(
                    json.dumps({"businessKey": bk, "response": ar.api_body},
                               ensure_ascii=False, indent=2, default=str), encoding="utf-8")
                data_ev.append("cases/" + spec.case_id + "/approve_response.json")
            evidence["data"] = data_ev
        except Exception:  # noqa: BLE001  证据落盘失败不影响判定
            pass

    return CaseResult(
        case_id=spec.case_id, verdict=verdict, details=details,
        cleanup_ok=cleanup_ok, duration_s=round(time.time() - t0, 3),
        title=spec.title, kind=spec.kind, mode=spec.mode,
        report={"did": did, "layers": layers, "evidence": evidence})
