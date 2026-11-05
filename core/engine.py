"""
写入类执行编排(ExecSpec 驱动):
  登记 → 造前置状态(data_prep)→ 前置快照 → 主写动作(+可选一键审批)
       → 校验(响应+库)→ diff 安全网 → 清理(按 marker 反删)。
控制流写死,执行期纯确定性,不碰 LLM。复用 ApiAdapter/Verifier/SnapshotGuard/Cleaner。
"""
from __future__ import annotations

import time

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
    }
    return TestCase(case_id=spec.case_id, feature=spec.feature or spec.case_id,
                    account_ref="", data_prep=None, steps=[], expected=expected, raw=raw)


def run_write_spec(spec, db: DbClient, *, base_url: str = "", session_file: str = "",
                   registry_path="." ) -> CaseResult:
    """执行一条写入类 ExecSpec,返回 CaseResult。db 需带写连接(清理用)。"""
    t0 = time.time()
    case = spec_to_testcase(spec)
    marker = make_marker(spec.case_id)
    adapter = ApiAdapter(base_url=base_url or spec.base_url, session_file=session_file or spec.session)
    guard = SnapshotGuard(db)
    verifier = Verifier(db)
    cleaner = Cleaner(db, registry_path)

    verdict, details = Verdict.PASS, []
    cleaner.register(case, marker)
    try:
        adapter.setup(case)

        for prep in (case.raw.get("data_prep") or []):
            r = adapter.call(prep, {"marker": marker})
            if not r.ok:
                details.append(f"data_prep 失败: {r.error or r.api_status}")

        guard.snapshot_before(case.expected)
        action = adapter.perform(case, marker)

        approve = case.raw.get("approve") or {}
        if approve:
            bk = _resolve_business_key(approve, action, db, marker)
            avars = {"marker": marker}
            if bk is not None:
                avars["businessKey"] = bk
            elif approve.get("business_key_from"):
                details.append("一键审批:未取到 businessKey(检查 business_key_from)")
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
            if not ar.ok:
                details.append(f"一键审批失败: {ar.error or ar.api_status}")
            for path, val in ((approve.get("expect") or {}).get("body") or {}).items():
                got = _dig(ar.api_body, path)
                if _MISSING is got or str(got) != str(val):
                    details.append(f"审批响应 {path}: 预期 {val!r} vs 实际 {got!r}")

        verdict, vdetails = verifier.verify(case, marker, action)
        details += vdetails

        dverdict, ddetails = guard.snapshot_after(case.expected, marker)
        if dverdict is not Verdict.PASS:
            details += ddetails
            if verdict is Verdict.PASS:
                verdict = dverdict
    except Exception as e:  # noqa: BLE001
        verdict, details = Verdict.ENV_ERROR, [f"执行异常: {e}"]
    finally:
        adapter.teardown()

    cleanup_ok = cleaner.cleanup(marker)
    return CaseResult(
        case_id=spec.case_id, verdict=verdict, details=details,
        cleanup_ok=cleanup_ok, duration_s=round(time.time() - t0, 3),
        title=spec.title, kind=spec.kind, mode=spec.mode)
