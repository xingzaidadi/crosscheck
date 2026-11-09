"""
写入类执行编排(ExecSpec 驱动):
  登记 → 造前置状态(data_prep)→ 前置快照 → 主写动作(+可选一键审批)
       → 校验(响应+库)→ diff 安全网 → 清理(按 marker 反删)。
控制流写死,执行期纯确定性,不碰 LLM。复用 ApiAdapter/Verifier/SnapshotGuard/Cleaner。
编排器 run_write_spec 只按序调各 _phase_*(读写同一 _WriteCtx);执行链顺序即代码顺序。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from adapters.api_adapter import ApiAdapter  # 仅作类型标注;构造一律走 connectors.make_adapter
from core.cleaner import Cleaner
from core.connectors import make_adapter
from core.interfaces import CaseResult, DbAssertion, Expected, TestCase, Verdict
from core.marker import make_marker
from core.snapshot import SnapshotGuard
from core.verifier import Verifier, _dig, _eq, _MISSING
from db.client import DbClient


def _render_where(where: str, vars: dict) -> str:
    """把 where 里的 {{AUTOTEST_标记值}}/{{var}} 换成当前 vars(业务配置,非外部输入)。"""
    out = where.replace("{{AUTOTEST_标记值}}", str(vars.get("marker", "")))
    for k, v in vars.items():
        out = out.replace("{{" + k + "}}", str(v))
    return out


def _db_scalar(db: DbClient, table: str, column: str, where: str):
    """查库取一个标量(column 可为表达式如 MAX(id)+999999);无行返回 None。"""
    rows = db.query(f"SELECT {column} AS v FROM {table} WHERE {where}")
    return rows[0]["v"] if rows else None


def _run_prep_step(prep: dict, adapter, db: DbClient, vars: dict) -> tuple[list[str], list[str]]:
    """执行一个 data_prep 步骤,返回 (did, env_reasons)。
    固定内部序:db_wait(轮询到状态翻转)→ db_capture(查库抓 itemId/version/businessKey 进 vars)
              → http(可选,可走独立 session/base_url,如 BPM 审批)→ 响应 capture。
    纯确定性;让"提交→审批→等状态→查库拿键→动作"这类多步流水线可全配置表达,免手搓脚本。"""
    did, env = [], []
    w = prep.get("db_wait")
    if w:
        where = _render_where(w["where"], vars)
        deadline = time.time() + float(w.get("timeout_s", 30))
        got = _db_scalar(db, w["table"], w["column"], where)
        while not _eq(got, w.get("equals")) and time.time() < deadline:
            time.sleep(float(w.get("interval_s", 2)))
            got = _db_scalar(db, w["table"], w["column"], where)
        did.append(f"等库 {w['table']}.{w['column']}={w.get('equals')}(实际 {got})")
        if not _eq(got, w.get("equals")):
            env.append(f"db_wait 超时: {w['table']}.{w['column']} 实际 {got} 期望 {w.get('equals')}")
            return did, env
    for var, q in (prep.get("db_capture") or {}).items():
        where = _render_where(q["where"], vars)
        val = _db_scalar(db, q["table"], q["column"], where)
        if val is None and q.get("poll_until_nonempty"):
            deadline = time.time() + float(q.get("timeout_s", 24))
            while val is None and time.time() < deadline:
                time.sleep(float(q.get("interval_s", 2)))
                val = _db_scalar(db, q["table"], q["column"], where)
        if val is None:
            env.append(f"db_capture 未取到 {var}({q['table']}.{q['column']})")
        else:
            vars[var] = val
            did.append(f"抓库 {var}={val}")
    if prep.get("url"):
        sess = prep.get("session")
        if sess:
            sub = make_adapter("api", base_url=prep.get("base_url", ""), session_file=sess)
            try:
                sub.setup()
                r = sub.call(prep, vars)
            finally:
                sub.teardown()
        else:
            r = adapter.call(prep, vars)
        did.append(f"造前置状态 {prep.get('method')} {prep.get('url')}")
        if not r.ok:
            env.append(f"data_prep 失败: {r.error or r.api_status}")
        for var, path in (prep.get("capture") or {}).items():
            val = _dig(r.api_body, path)
            if val is _MISSING:
                env.append(f"data_prep 未抓到 {var}(路径 {path})")
            else:
                vars[var] = val
    return did, env


def _resolve_business_key(approve: dict, action, db: DbClient, marker: str):
    """审批前拿 businessKey:优先从提交响应取(response 路径),否则按 marker 查库。"""
    bkf = approve.get("business_key_from") or {}
    if bkf.get("response"):
        if action is None:        # 审批前置于主动作:无动作响应可取,退 None(交由 db/vars 兜底,不崩)
            return None
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
                    row_count=a.get("row_count"), row_count_min=a.get("row_count_min"),
                    fields=a.get("fields") or {})
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
        "steps": getattr(spec, "steps", None) or [],
        "verify_poll": spec.verify_poll,
        "event_asserts": spec.assertions.get("events") or [],
        "roundtrip": spec.assertions.get("roundtrip") or {},
        "unchanged": spec.assertions.get("unchanged") or {},
        "idempotent": spec.assertions.get("idempotent") or {},
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
        cnt_ok = (a.row_count is None or len(got_rows) == a.row_count) and \
                 (a.row_count_min is None or len(got_rows) >= a.row_count_min)
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


@dataclass
class _WriteCtx:
    """写入类执行的共享上下文:累加器(判定/明细/层/做了什么/失败与前置原因)+ 句柄。
    各相位(_phase_*)读写同一 ctx;编排器只按序调相位——执行链顺序即代码顺序,
    与单函数版逐行等价。_fail_if_pass 封装"仅在仍为 PASS 时下调为 FAIL"这一高频判定。"""
    spec: Any
    case: TestCase
    db: DbClient
    adapter: ApiAdapter
    guard: SnapshotGuard
    verifier: Verifier
    marker: str
    req: dict
    code_path: str
    base_url: str
    session_file: str
    vars: dict = field(default_factory=dict)
    verdict: Verdict = Verdict.PASS
    details: list = field(default_factory=list)
    did: list = field(default_factory=list)
    layers: list = field(default_factory=list)
    fail_reasons: list = field(default_factory=list)
    env_reasons: list = field(default_factory=list)
    action: Any = None
    ar: Any = None
    bk: Any = None
    uc_before: Any = None

    def _fail_if_pass(self) -> None:
        if self.verdict is Verdict.PASS:
            self.verdict = Verdict.FAIL


# ── 统一 SetupStep 协议 ──────────────────────────────────────────────
# 造数/审批/等库/抓库 本质都是"按序执行、改状态、可抓变量"的步骤。统一成一个
# 步骤执行器(_run_setup / _run_approve / 主动作),既被常规相位调用,也被有序
# 流水线 _phase_pipeline 调用——审批不再被写死在"主动作之后",可在流水线里任意
# 落位(kind: approve)。142 条老用例不配 steps,仍走常规相位,逐行等价不回归。

def _run_setup(c: _WriteCtx, step: dict) -> None:
    """一个造数/等库/抓库步骤(复合:db_wait→db_capture→http);penv 同时进明细与前置原因。"""
    pdid, penv = _run_prep_step(step, c.adapter, c.db, c.vars)
    c.did += pdid
    for m in penv:
        c.details.append(m)
        c.env_reasons.append(m)


def _phase_data_prep(c: _WriteCtx) -> None:
    """前置造数:逐个发请求造出所需状态单;capture 把返回里的值(如单号)抓进 vars,
    供主动作/审批/断言用 {{var}} 引用(状态守卫/流转/编辑类用例的前提)。"""
    for prep in (c.case.raw.get("data_prep") or []):
        _run_setup(c, prep)


def _phase_unchanged_before(c: _WriteCtx) -> None:
    """副作用防护:操作前给目标记录拍字段快照(守卫/负向用例用)。"""
    uc = c.case.raw.get("unchanged") or {}
    if uc.get("table"):
        from core import unchanged as _uc
        c.uc_before = _uc.read_fields(c.db, uc["table"],
                                      _uc.render_where(uc["where"], c.marker, c.vars), uc.get("fields"))


def _phase_action(c: _WriteCtx) -> None:
    """前置快照 + 主写动作 + 提交接口层。期望成功的写动作却失败 → 执行未成立
    (负向用例 rejected 期望失败,不算)。"""
    c.guard.snapshot_before(c.case.expected)
    c.action = c.adapter.perform(c.case, c.marker, c.vars)
    c.did.append(f"执行写动作 {c.req.get('method')} {c.req.get('url')}(唯一标记 {c.marker})")
    code = _dig(c.action.api_body, "code")
    doc_no = _dig(c.action.api_body, c.code_path)
    c.layers.append({
        "name": "提交接口", "ok": bool(c.action.ok),
        "expected": "HTTP<400 且业务 code=0,生成单据",
        "actual": f"HTTP {c.action.api_status} · code={'—' if code is _MISSING else code}"
                  f" · 单号={'—' if doc_no is _MISSING else doc_no}",
        "note": str(c.action.api_body)[:300]})
    if not c.action.ok and not (c.case.raw.get("response_assert") or {}).get("rejected"):
        c.env_reasons.append(f"主写动作失败: HTTP {c.action.api_status}(期望成功)")


def _phase_approve(c: _WriteCtx) -> None:
    """常规相位:执行 spec.approve(若有)。流水线模式改由 _run_approve 按位置调用。"""
    _run_approve(c, c.case.raw.get("approve") or {})


def _run_approve(c: _WriteCtx, approve: dict) -> None:
    """一键审批步骤:解析 businessKey → 走独立鉴权 session(审批主机常与业务站不同域)
    调审批接口 → 校响应。传输失败或响应不符预期记 fail_reasons(执行链未成立)。
    不再写死在主动作之后——可作为 steps 流水线里的一步任意落位。"""
    if not approve:
        return
    c.bk = _resolve_business_key(approve, c.action, c.db, c.marker)
    avars = dict(c.vars)
    if c.bk is not None:
        avars["businessKey"] = c.bk
    elif approve.get("business_key_from"):
        c.details.append("一键审批:未取到 businessKey(检查 business_key_from)")
    c.did.append(f"BPM 审批 {approve.get('method')} {approve.get('url')}(businessKey={c.bk})")
    appr_session = approve.get("session")
    if appr_session:
        appr = make_adapter("api", base_url=approve.get("base_url", ""), session_file=appr_session)
        try:
            appr.setup()
            c.ar = appr.call(approve, avars)
        finally:
            appr.teardown()
    else:
        c.ar = c.adapter.call(approve, avars)
    appr_ok = c.ar.ok
    appr_notes = []
    if not c.ar.ok:
        appr_ok = False
        c.details.append(f"一键审批失败: {c.ar.error or c.ar.api_status}")
    for path, val in ((approve.get("expect") or {}).get("body") or {}).items():
        got = _dig(c.ar.api_body, path)
        if _MISSING is got or str(got) != str(val):
            appr_ok = False
            c.details.append(f"审批响应 {path}: 预期 {val!r} vs 实际 {got!r}")
            appr_notes.append(f"{path}: 预期 {val} vs 实际 {got}")
    c.layers.append({
        "name": "BPM 审批", "ok": appr_ok,
        "expected": "审批接口返回 " + str((approve.get("expect") or {}).get("body") or "HTTP<400"),
        "actual": f"HTTP {c.ar.api_status} · {str(c.ar.api_body)[:160]}",
        "note": "; ".join(appr_notes)})
    if not appr_ok:
        c.fail_reasons.append("审批未通过(传输失败或响应不符预期)")


def _phase_pipeline(c: _WriteCtx) -> None:
    """有序步骤流水线(spec.steps):造数/主动作/审批视作同一种"步",按声明序执行——
    审批可落在主动作前后任意位置,解除"审批必须在主动作之后"的写死约束。
    step.kind:action=主写动作(连带前置快照+副作用前拍);approve=一键审批;
    其余=造数复合步(db_wait→db_capture→http)。老用例不配 steps,仍走常规相位。"""
    for step in (c.case.raw.get("steps") or []):
        kind = (step or {}).get("kind", "setup")
        if kind == "action":
            _phase_unchanged_before(c)
            _phase_action(c)
        elif kind == "approve":
            _run_approve(c, step)
        else:
            _run_setup(c, step)


def _phase_verify(c: _WriteCtx) -> None:
    """内核多源校验(响应 + 库断言),在此设定 verdict;后续不变量相位只在仍 PASS 时下调。"""
    c.verdict, vdetails = c.verifier.verify(c.case, c.marker, c.action, c.vars)
    c.details += vdetails


def _phase_idempotent(c: _WriteCtx) -> None:
    """幂等不变量:同参再发一次,两次应返回同一单据(不同=没幂等,重复建单)。
    放在 verify 后,避免被覆盖。"""
    idem = c.case.raw.get("idempotent") or {}
    if not idem:
        return
    from core import invariants as _inv
    r2 = c.adapter.call(c.req, c.vars)
    path = idem.get("code_from", c.code_path)
    id1, id2 = _dig(c.action.api_body, path), _dig(r2.api_body, path)
    iok = _inv.idempotent_ok(id1, id2)
    c.layers.append({"name": "幂等不变量", "ok": iok,
                     "expected": "同参重复请求返回同一单据,不重复生成",
                     "actual": f"第1次 {id1} · 第2次 {id2}"})
    if not iok:
        c.details.append(f"幂等失效:两次返回不同单据 {id1!r} vs {id2!r}")
        c._fail_if_pass()


def _phase_events(c: _WriteCtx) -> None:
    """异步/事件校验:等事件表/外部通知在时限内按标记落地(事件消费/异步导出/飞书/MQ)。"""
    ev_asserts = c.case.raw.get("event_asserts") or []
    if not ev_asserts:
        return
    from core.events import check_events
    eok, edetails, elayers = check_events(
        ev_asserts, marker=c.marker, vars=c.vars, db=c.db,
        base_url=c.adapter.base_url, session_file=c.spec.session)
    c.details += edetails
    c.layers += elayers
    if not eok:
        c._fail_if_pass()


def _phase_roundtrip(c: _WriteCtx) -> None:
    """全字段对账:写后拉详情,把提交体逐字段比持久化记录(漏填/改写/截断现形)
    + 计算不变量(金额重算等,复用同一次详情)。"""
    rt = c.case.raw.get("roundtrip") or {}
    if not (rt and rt.get("detail") and c.action is not None):
        return
    from core import roundtrip as _rt
    code = _dig(c.action.api_body, rt.get("code_from", c.code_path))
    if code is _MISSING:
        c.details.append("全字段对账:未取到单号(检查 code_from)")
        return
    det = rt["detail"]
    ad2 = make_adapter("api", base_url=det.get("base_url") or c.adapter.base_url,
                       session_file=det.get("session") or c.session_file or c.spec.session)
    try:
        ad2.setup()
        dr = ad2.call(det, {**c.vars, "code": code})
    finally:
        ad2.teardown()
    persisted = _dig(dr.api_body, rt.get("detail_data_path", "data"))
    submitted = c.adapter._render(c.req.get("body"), c.vars)
    rok, mism, rlayer = _rt.compare(
        submitted, persisted if persisted is not _MISSING else {},
        ignore=rt.get("ignore") or [], item_key=rt.get("item_key", ""),
        item_ignore=rt.get("item_ignore") or [])
    pdata = persisted if persisted is not _MISSING else {}
    if rt.get("fields", True):
        c.layers.append(rlayer)
        if not rok:
            c.details += [f"字段不一致: {m[0]} 提交{m[1]!r} vs 落库{m[2]!r}" for m in mism]
            c._fail_if_pass()
    if rt.get("compute"):
        from core import invariants as _inv
        cok, clayer = _inv.check_compute(submitted, pdata, rt["compute"],
                                         item_key=rt.get("item_key", ""))
        c.layers.append(clayer)
        if not cok:
            c.details += [f"计算不变量不符: {r[0]} {r[1]}={r[2]} vs 落库{r[3]}"
                          for r in clayer.get("rows", []) if r[-1] == "✗"]
            c._fail_if_pass()


def _phase_unchanged_after(c: _WriteCtx) -> None:
    """副作用防护:操作后再拍,比前后快照——不该变却变了的字段现形。"""
    uc = c.case.raw.get("unchanged") or {}
    if not uc.get("table"):
        return
    from core import unchanged as _uc
    uc_after = _uc.read_fields(c.db, uc["table"],
                               _uc.render_where(uc["where"], c.marker, c.vars), uc.get("fields"))
    uok, ulayer = _uc.diff(c.uc_before, uc_after, uc.get("fields"))
    c.layers.append(ulayer)
    if not uok:
        c.details += [f"副作用:字段 {r[0]} 被改 {r[1]!r}→{r[2]!r}" for r in ulayer.get("rows", []) if r[-1] == "✗"]
        c._fail_if_pass()


def _phase_snapshot_after(c: _WriteCtx) -> None:
    """全库 diff 安全网(异常只在仍 PASS 时下调)+ 库断言富报告层。"""
    dverdict, ddetails = c.guard.snapshot_after(c.case.expected, c.marker)
    if dverdict is not Verdict.PASS:
        c.details += ddetails
        if c.verdict is Verdict.PASS:
            c.verdict = dverdict
    if c.case.expected.db:
        c.layers.append(_db_assert_layer(c.case, c.db, c.marker, c.vars))


def _phase_integrity_gate(c: _WriteCtx) -> None:
    """执行链完整性收口(阶段0 防假通过):前置/审批/主动作未成立,绝不判 PASS。"""
    if c.fail_reasons and c.verdict is Verdict.PASS:
        c.verdict = Verdict.FAIL
        c.details = ["执行链失败,不计通过:"] + c.fail_reasons + c.details
    if c.env_reasons and c.verdict is Verdict.PASS:
        c.verdict = Verdict.ENV_ERROR
        c.details = ["前置未成立,不计通过:"] + c.env_reasons + c.details


def _dump_evidence(c: _WriteCtx, run_dir) -> dict:
    """落盘动作/审批的请求与响应到 runs/<ts>/cases/<id>/,供事后取证;失败不影响判定。"""
    evidence: dict = {}
    if run_dir is None:
        return evidence
    try:
        case_dir = Path(run_dir) / "cases" / c.spec.case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        rendered = c.adapter._render(c.req.get("body"), {"marker": c.marker})
        (case_dir / "api_request.json").write_text(
            json.dumps({"method": c.req.get("method"), "url": c.req.get("url"), "body": rendered},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        (case_dir / "api_response.json").write_text(
            json.dumps(c.action.api_body if c.action else None, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
        data_ev = ["cases/" + c.spec.case_id + "/api_request.json",
                   "cases/" + c.spec.case_id + "/api_response.json"]
        if c.ar is not None:
            (case_dir / "approve_response.json").write_text(
                json.dumps({"businessKey": c.bk, "response": c.ar.api_body},
                           ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            data_ev.append("cases/" + c.spec.case_id + "/approve_response.json")
        evidence["data"] = data_ev
    except Exception:  # noqa: BLE001  证据落盘失败不影响判定
        pass
    return evidence


def run_write_spec(spec, db: DbClient, *, base_url: str = "", session_file: str = "",
                   registry_path=".", run_dir=None) -> CaseResult:
    """执行一条写入类 ExecSpec,返回 CaseResult(含富报告层)。db 需带写连接(清理用)。
    控制流写死、纯确定性:按序跑各相位(见 _phase_*),不碰 LLM。"""
    t0 = time.time()
    case = spec_to_testcase(spec)
    marker = make_marker(spec.case_id)
    c = _WriteCtx(
        spec=spec, case=case, db=db,
        adapter=make_adapter("api", base_url=base_url or spec.base_url, session_file=session_file or spec.session),
        guard=SnapshotGuard(db, full_scan=getattr(spec, "diff_full_scan", True)),
        verifier=Verifier(db), marker=marker,
        req=case.raw.get("request") or {},
        code_path=getattr(spec, "code_path", "") or "data.code",   # 单据号路径:route 配(业务),core 退通用默认
        base_url=base_url, session_file=session_file,
        vars={"marker": marker})
    cleaner = Cleaner(db, registry_path)
    cleaner.register(case, marker)
    try:
        c.adapter.setup(case)
        if case.raw.get("steps"):
            _phase_pipeline(c)           # 有序流水线:造数/主动作/审批自由落位
        else:
            _phase_data_prep(c)          # 常规:造数 → 副作用前拍 → 主动作 → 审批
            _phase_unchanged_before(c)
            _phase_action(c)
            _phase_approve(c)
        _phase_verify(c)
        _phase_idempotent(c)
        _phase_events(c)
        _phase_roundtrip(c)
        _phase_unchanged_after(c)
        _phase_snapshot_after(c)
        _phase_integrity_gate(c)
    except Exception as e:  # noqa: BLE001
        c.verdict, c.details = Verdict.ENV_ERROR, [f"执行异常: {e}"]
        c.layers.append({"name": "执行异常", "ok": False, "note": str(e)})
    finally:
        c.adapter.teardown()

    cleanup_ok = cleaner.cleanup(marker)
    n_child = sum(1 for t in (case.raw.get("cleanup_targets") or []) if t.get("parent"))
    c.did.append(f"清理:按标记删主表 + 按父单号删 {n_child} 张子表")
    c.layers.append({
        "name": "数据清理", "ok": cleanup_ok,
        "expected": "本次造数全部反删,registry 销账",
        "actual": "已销账(全删成功)" if cleanup_ok else "部分未清,标 cleanup_pending",
        "note": f"主表按标记列反删;{n_child} 张子表按父单号(父表标记列命中)反查删"})

    evidence = _dump_evidence(c, run_dir)

    return CaseResult(
        case_id=spec.case_id, verdict=c.verdict, details=c.details,
        cleanup_ok=cleanup_ok, duration_s=round(time.time() - t0, 3),
        title=spec.title, kind=spec.kind, mode=spec.mode,
        report={"did": c.did, "layers": c.layers, "evidence": evidence})
