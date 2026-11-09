"""
批量执行入口:读一批用例 → 逐条执行 → 出汇总报告。

  # 直接喂固定格式 Excel(自动草拟规格,未建模的透明跳过):
  python run_batch.py --excel <workspace>/cases/xxx.xlsx --limit 10 --out report.html

  # 跑已建模并人审过的规格(workspace/specs/*.yaml):
  python run_batch.py --specs <workspace>/specs --out report.html

执行方式(按规格 mode):
  reconcile —— 查询类:复用对账链(接口样本 vs 库),给 PASS/FAIL。
  api/ui    —— 写入/UI 类:Phase 2 实现,当前透明跳过并说明。
未人审(verify_status != human_verified)的规格一律跳过,提示先补全建模。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.workspace import set_workspace, workspace_root, kb_dir, captures_dir, config_dir  # noqa: E402
from core.case_source import read_cases  # noqa: E402
from core.spec import ExecSpec, from_raw, load_specs  # noqa: E402
from core.modeler import model_cases, load_routes  # noqa: E402
from core.parallel import run_pool  # noqa: E402
from core.reporter import Reporter  # noqa: E402
from core.interfaces import CaseResult, Verdict  # noqa: E402
from core.reconciler import Reconciler  # noqa: E402
from core import engine, ui_check, run_report  # noqa: E402
from core.config import db_config, db_params  # noqa: E402
from db.client import DbClient  # noqa: E402


def _open_db(db_name: str = "") -> DbClient | None:
    cfg = db_config()
    if cfg.get("databases"):
        name = db_name or cfg.get("default_readonly")
        p = db_params(name) if name else None
        if p:
            return DbClient(readonly_params=p)
    ro = (cfg.get("readonly") or {}).get("dsn", "")
    if ro and "TODO" not in ro:
        return DbClient(dsn_readonly=ro)
    return None


def _filters(body: dict) -> dict:
    skip = {"pagenum", "pageno", "pagesize", "offset", "limit", "size"}
    return {k: v for k, v in (body or {}).items()
            if v not in ("", [], None) and k.lower() not in skip}


def _run_reconcile(spec: ExecSpec, case_dir: Path | None = None) -> tuple[Verdict, list[str], dict]:
    feature = spec.feature or spec.case_id
    mapping_path = Path(spec.mapping) if spec.mapping else kb_dir() / "query_mapping" / f"{feature}.json"
    sample_path = Path(spec.sample) if spec.sample else captures_dir() / f"{feature}_picked.json"
    rep = {"did": [], "layers": [], "evidence": {}}
    if not mapping_path.exists():
        return Verdict.SKIP, [f"未建模:缺映射 {mapping_path.name}"], {
            **rep, "layers": [{"name": "建模", "ok": False, "note": f"缺映射 {mapping_path.name}(先 run_verify probe + 人审)"}]}
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))

    if spec.request:
        from core.connectors import make_adapter
        method = (spec.request.get("method") or "GET").upper()
        url = spec.request.get("url", "")
        flt = _filters(spec.request.get("body") or {})
        rep["did"].append(f"调用接口 {method} {url}" + (f",筛选 {flt}" if flt else "(默认无筛选)"))
        ad = make_adapter("api", base_url=spec.base_url, session_file=spec.session)
        try:
            ad.setup(); r = ad.call(spec.request, {})
        finally:
            ad.teardown()
        if not r.ok:
            return Verdict.ENV_ERROR, [f"接口调用失败 status={r.api_status}"], {
                **rep, "layers": [{"name": "接口调用", "ok": False,
                                   "actual": f"HTTP {r.api_status}", "note": str(r.api_body)[:200]}]}
        api_params = spec.request.get("body") or {}
        api_resp = r.api_body or {}
    else:
        if not sample_path.exists():
            return Verdict.SKIP, [f"缺抓包样本 {sample_path.name}"], {
                **rep, "layers": [{"name": "样本", "ok": False, "note": f"缺 {sample_path.name}(配 request 现调或先 probe)"}]}
        picked = json.loads(sample_path.read_text(encoding="utf-8"))
        api_params = picked.get("request_body") or picked.get("query_params") or {}
        api_resp = picked.get("response_json") or {}
        rep["did"].append(f"读抓包样本 {sample_path.name}")

    db = _open_db(spec.db)
    if db is None:
        return Verdict.ENV_ERROR, ["未配可用只读库,无法对账"], {
            **rep, "layers": [{"name": "连库", "ok": False, "note": "workspace/config/db.yaml 未配可用只读库"}]}
    try:
        res = Reconciler(db, mapping).reconcile(api_params, api_resp)
    except Exception as e:  # noqa: BLE001  单条对账出错不拖垮整批
        return Verdict.ENV_ERROR, [f"对账执行异常: {e}"], {
            **rep, "layers": [{"name": "接口 ↔ 库 对账", "ok": False,
                               "note": f"异常(多为映射库/表不匹配):{str(e)[:200]}"}]}
    finally:
        db.close()
    rep["did"].append(f"连库 {spec.db or 'default'},按『{feature}』映射把接口参数翻成 SQL 对账")
    rep["layers"].append(run_report.reconcile_layer(res, mapping))

    if case_dir is not None:
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "api_response.json").write_text(
            json.dumps(api_resp, ensure_ascii=False, indent=2), encoding="utf-8")
        (case_dir / "reconcile.json").write_text(json.dumps({
            "table": res.table, "from_clause": res.from_clause, "where_sql": res.where_sql,
            "count_sql": res.count_sql, "api_total": res.api_total, "db_total": res.db_total,
            "field_samples": res.field_samples}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        rep["evidence"]["data"] = ["cases/" + case_dir.name + "/api_response.json",
                                   "cases/" + case_dir.name + "/reconcile.json"]

    verdict = Verdict.PASS if res.consistent else Verdict.FAIL
    details = ["对账一致"] if res.consistent else res.render().splitlines()
    return verdict, details, rep


def _open_rw(spec: ExecSpec):
    """开读写连接。返回 (DbClient|None, has_write)。写账号来自 db.yaml default_write。"""
    cfg = db_config()
    if cfg.get("databases"):
        ro_name = spec.db or cfg.get("default_readonly")
        wr_name = cfg.get("default_write") or (f"{spec.db}_write" if spec.db else None)
        ro = db_params(ro_name) if ro_name else None
        wr = db_params(wr_name) if wr_name else None
        if ro:
            return DbClient(readonly_params=ro, write_params=wr), bool(wr)
    ro_dsn = (cfg.get("readonly") or {}).get("dsn", "")
    wr_dsn = (cfg.get("write") or {}).get("dsn", "")
    if ro_dsn and "TODO" not in ro_dsn:
        return DbClient(dsn_readonly=ro_dsn, dsn_write=wr_dsn or None), bool(wr_dsn and "TODO" not in wr_dsn)
    return None, False


def _skip(spec, t0, detail, verdict=Verdict.SKIP, layer="状态") -> CaseResult:
    return CaseResult(case_id=spec.case_id, verdict=verdict, details=[detail],
                      duration_s=round(time.time() - t0, 3),
                      title=spec.title, kind=spec.kind, mode=spec.mode,
                      report={"did": [], "layers": [{"name": layer, "ok": False, "note": detail}],
                              "evidence": {}})


def execute(spec: ExecSpec, dry_run: bool, run_dir: Path, no_cleanup: bool = False) -> CaseResult:
    t0 = time.time()
    case_dir = run_dir / "cases" / spec.case_id

    if dry_run:
        return _skip(spec, t0, f"dry-run:仅草拟(kind={spec.kind}, mode={spec.mode}, 接口={spec.endpoints or '—'})", layer="dry-run")
    if getattr(spec, "blocked", ""):
        return _skip(spec, t0, f"待确认-阻塞:{spec.blocked}(保留设计,不计通过)", layer="待确认门禁")
    if spec.verify_status != "human_verified":
        return _skip(spec, t0, "未人审(draft):补全 assertions / request 并转 human_verified 后再执行", layer="人审")

    # 前置状态:声明 prepare_state 则按配方展开成 data_prep(造出该状态的单)
    if getattr(spec, "prepare_state", "") and not spec.data_prep:
        from core.state_recipe import recipe_steps, available_states
        steps = recipe_steps(spec.feature, spec.prepare_state)
        if not steps:
            return _skip(spec, t0, f"缺状态配方:{spec.feature}/{spec.prepare_state}"
                                   f"(可用 {available_states(spec.feature) or '无'};在 state_recipes/ 配)", layer="前置状态")
        spec.data_prep = steps

    if spec.mode == "reconcile":
        verdict, details, rep = _run_reconcile(spec, case_dir)
        return CaseResult(case_id=spec.case_id, verdict=verdict, details=details,
                          duration_s=round(time.time() - t0, 3),
                          title=spec.title, kind=spec.kind, mode=spec.mode, report=rep)

    if spec.mode in ("api", "write"):
        if not spec.request:
            return _skip(spec, t0, "未建模:缺 request(写动作),补全后再执行")
        db, has_write = _open_rw(spec)
        if db is None:
            return _skip(spec, t0, "未配可用库(workspace/config/db.yaml)", verdict=Verdict.ENV_ERROR)
        if not has_write:
            db.close()
            return _skip(spec, t0, "未配写库账号(db.yaml default_write):写入类暂不执行,避免留脏数据")
        try:
            cr = engine.run_write_spec(spec, db, run_dir=run_dir,
                                       registry_path=workspace_root() / ".cleanup_registry.json",
                                       no_cleanup=no_cleanup)
        finally:
            db.close()
        if not cr.report:
            cr.report = {"did": [f"调用写接口 {spec.request.get('method')} {spec.request.get('url')}"],
                         "layers": [{"name": "写入执行", "ok": cr.verdict is Verdict.PASS,
                                     "note": "; ".join(cr.details)}], "evidence": {}}
        return cr

    if spec.mode == "ui":
        if (spec.ui or {}).get("page_model"):   # UI 写入:回放 page_model → 提交 → 验库 → 清理
            db, has_write = _open_rw(spec)
            if db is None:
                return _skip(spec, t0, "未配可用库(workspace/config/db.yaml)", verdict=Verdict.ENV_ERROR)
            try:
                return ui_check.run_ui_write_spec(spec, db, run_dir, no_cleanup=no_cleanup)
            finally:
                db.close()
        db = _open_db(spec.db)                   # UI 读:库↔接口↔页面 三层校验
        try:
            return ui_check.run_ui_spec(spec, db, run_dir)
        finally:
            if db is not None:
                db.close()

    return _skip(spec, t0, f"{spec.mode} 模式暂不支持")


def run_specs(specs, dry_run, run_dir, workers: int = 1, no_cleanup: bool = False, pace: float = 0):
    """调度执行:只读(reconcile)类可并发(互不影响);写入/UI 串行(快照需安静库)。保序返回。"""
    if workers <= 1:
        out = []
        for i, s in enumerate(specs, 1):
            print(f"  [{i}/{len(specs)}] {s.case_id} {s.title[:40]} …", flush=True)
            out.append(execute(s, dry_run, run_dir, no_cleanup))
        return out
    results = [None] * len(specs)
    read = [i for i, s in enumerate(specs) if s.mode == "reconcile"]
    other = [i for i, s in enumerate(specs) if s.mode != "reconcile"]
    print(f"  并发只读 {len(read)} 条(workers={workers})+ 串行写入/UI {len(other)} 条")
    for i, r in zip(read, run_pool([specs[i] for i in read],
                                   lambda s: execute(s, dry_run, run_dir, no_cleanup), workers)):
        results[i] = r
    import time as _t
    for n, i in enumerate(other):
        print(f"  [串行] {specs[i].case_id} {specs[i].title[:40]} …", flush=True)
        results[i] = execute(specs[i], dry_run, run_dir, no_cleanup)
        # 节奏控制:写入/BPM 类用例背靠背会打爆共享环境(submit 400、BPM 异步滞后、db_wait 超时),
        # 条间留间隔让环境/BPM 跟上;最后一条不等。pace=0 关闭(默认)。
        if pace and n < len(other) - 1:
            _t.sleep(pace)
    return results


def main():
    ap = argparse.ArgumentParser(description="批量执行用例 → 汇总报告")
    ap.add_argument("--workspace", default=None, help="业务数据目录")
    ap.add_argument("--excel", default=None, help="固定格式 Excel 用例(自动草拟规格)")
    ap.add_argument("--sheet", default=None, help="Excel sheet 名(默认第一个)")
    ap.add_argument("--specs", default=None, help="已建模规格目录(*.yaml)")
    ap.add_argument("--with-specs", dest="with_specs", default=None,
                    help="(配 --excel)额外合并人审规格目录(逗号分隔):UI/自定义类按 case_id 并入主套,"
                         "同号以额外规格为准。让一条命令覆盖 接口+UI+自定义。")
    ap.add_argument("--auto-model", dest="auto_model", action="store_true",
                    help="(配 --excel)自动建模:复用自发现产物(路由+映射+抓包)拼出可跑规格再执行")
    ap.add_argument("--save-specs", dest="save_specs", default=None,
                    help="(配 --auto-model)把自动建模出的规格落盘到该目录,便于人审")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条(0=全部)")
    ap.add_argument("--only", default=None, help="只跑这些 case_id(逗号分隔,如 TC22,TC21),用于定点复跑")
    ap.add_argument("--dry-run", action="store_true", help="只草拟/校验,不连库执行")
    ap.add_argument("--run-id", dest="run_id", default=None, help="运行标识(默认 run_时间戳)")
    ap.add_argument("--run-dir", dest="run_dir", default=None, help="运行目录(默认 <workspace>/runs/<run-id>)")
    ap.add_argument("--workers", type=int, default=1, help="只读(对账)类并发数;写入/UI 仍串行。默认 1=全串行")
    ap.add_argument("--pace", type=float, default=0, help="写入/BPM 类用例条间间隔秒数(防背靠背打爆共享环境/BPM);0=不限速")
    ap.add_argument("--ensure-login", dest="ensure_login", action="store_true",
                    help="跑批前自动续期:对本批用到的 B 模式站点检活,失效则自动重登(A 模式失效仅告警)")
    ap.add_argument("--no-cleanup", dest="no_cleanup", action="store_true",
                    help="保留现场:写入/UI 类造数不反删(供人工复核/看前端)。不登记 registry,后续跑批不误删")
    ap.add_argument("--out", default=None, help="(已弃用)报告现固定输出到运行目录 report.html")
    args = ap.parse_args()

    if args.workspace:
        set_workspace(args.workspace)

    if args.excel:
        raws = read_cases(args.excel, args.sheet)
        if args.auto_model:
            routes = load_routes(config_dir() / "case_routes.yaml")
            specs = model_cases(raws, routes=routes, kb_root=kb_dir(), caps_root=captures_dir())
            ready = sum(1 for s in specs if s.verify_status == "human_verified")
            print(f"[batch] 从 Excel 自动建模 {len(specs)} 条,其中 {ready} 条可直接执行:{args.excel}")
            if args.save_specs:
                from core.spec import dump_spec
                for s in specs:
                    dump_spec(s, Path(args.save_specs) / f"{s.case_id}.yaml")
                print(f"[batch] 自动建模规格已落盘(待人审):{args.save_specs}")
        else:
            specs = [from_raw(c) for c in raws]
            print(f"[batch] 从 Excel 读入并草拟 {len(specs)} 条规格:{args.excel}")
    elif args.specs:
        specs = load_specs(args.specs)
        print(f"[batch] 载入已建模规格 {len(specs)} 条:{args.specs}")
    else:
        print("  ✗ 需指定 --excel 或 --specs"); sys.exit(2)

    # 合并额外人审规格(UI/自定义):同 case_id 以额外规格覆盖,新增的追加——一条命令覆盖 接口+UI+自定义
    if args.with_specs:
        by_id = {s.case_id: s for s in specs}
        added = 0
        for d in [x.strip() for x in args.with_specs.split(",") if x.strip()]:
            for es in load_specs(d):
                if es.verify_status == "human_verified":
                    if es.case_id not in by_id:
                        added += 1
                    by_id[es.case_id] = es
        specs = list(by_id.values())
        print(f"[batch] 合并额外人审规格:{args.with_specs} → 新增 {added},现共 {len(specs)} 条")

    if args.only:
        want = {x.strip() for x in args.only.split(",") if x.strip()}
        specs = [s for s in specs if s.case_id in want]
        print(f"[batch] --only 过滤后 {len(specs)} 条: {sorted(s.case_id for s in specs)}")
    if args.limit > 0:
        specs = specs[:args.limit]

    # 一次运行 = 一个文件夹:report.html + cases/<用例>/(截图/录像/数据)
    run_id = args.run_id or f"run_{time.strftime('%Y%m%d_%H%M%S')}"
    run_dir = Path(args.run_dir) if args.run_dir else (workspace_root() / "runs" / run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"[batch] 运行目录: {run_dir}")

    if args.ensure_login and not args.dry_run:
        from core.session_ensure import ensure_batch_sessions
        for a in ensure_batch_sessions(specs):
            tag = {"ensured": "✓ 续期/检活", "skip-manual": "⚠ A模式需人工", "error": "✗ 续期失败"}.get(a["action"], a["action"])
            print(f"  [登录] {a['site']}: {tag}" + (f" {a.get('error','')}" if a["action"] == "error" else ""))

    if args.no_cleanup and not args.dry_run:
        print("[batch] ⚠ --no-cleanup:写入/UI 类造数将保留不清理(保留现场)")
    results = run_specs(specs, args.dry_run, run_dir, args.workers, args.no_cleanup, args.pace)

    reporter = Reporter()
    for r in results:
        reporter.add(r)
    print("\n" + reporter.render())

    report_path = run_report.render(run_id, results, run_dir)
    # 用例/数据/报告都在 run 文件夹里,自成一体
    print(f"\n  ✓ 报告: {report_path}")
    print(f"  ✓ 该次全部资料在: {run_dir}")
    index_path = run_report.render_index(run_dir.parent)   # 跨运行总览(通过率趋势 + 直达各报告)
    if index_path:
        print(f"  ✓ 运行总览: {index_path}")

    from core.triage import summarize   # 失败自动归因:环境/建模错/真bug候选
    tr = summarize(results)
    nonpass = {k: v for k, v in tr["buckets"].items() if k not in ("pass", "skipped")}
    if nonpass:
        print(f"  ✓ 失败归因: {nonpass}")
        if tr["bug_candidates"]:
            print(f"  ⚠ 疑似缺陷(建议开发确认): {tr['bug_candidates']}")


if __name__ == "__main__":
    main()
