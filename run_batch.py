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

from core.workspace import set_workspace, workspace_root, kb_dir, captures_dir  # noqa: E402
from core.case_source import read_cases  # noqa: E402
from core.spec import ExecSpec, from_raw, load_specs  # noqa: E402
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
        from adapters.api_adapter import ApiAdapter
        method = (spec.request.get("method") or "GET").upper()
        url = spec.request.get("url", "")
        flt = _filters(spec.request.get("body") or {})
        rep["did"].append(f"调用接口 {method} {url}" + (f",筛选 {flt}" if flt else "(默认无筛选)"))
        ad = ApiAdapter(base_url=spec.base_url, session_file=spec.session)
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


def execute(spec: ExecSpec, dry_run: bool, run_dir: Path) -> CaseResult:
    t0 = time.time()
    case_dir = run_dir / "cases" / spec.case_id

    if dry_run:
        return _skip(spec, t0, f"dry-run:仅草拟(kind={spec.kind}, mode={spec.mode}, 接口={spec.endpoints or '—'})", layer="dry-run")
    if spec.verify_status != "human_verified":
        return _skip(spec, t0, "未人审(draft):补全 assertions / request 并转 human_verified 后再执行", layer="人审")

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
                                       registry_path=workspace_root() / ".cleanup_registry.json")
        finally:
            db.close()
        if not cr.report:
            cr.report = {"did": [f"调用写接口 {spec.request.get('method')} {spec.request.get('url')}"],
                         "layers": [{"name": "写入执行", "ok": cr.verdict is Verdict.PASS,
                                     "note": "; ".join(cr.details)}], "evidence": {}}
        return cr

    if spec.mode == "ui":
        db = _open_db(spec.db)
        try:
            return ui_check.run_ui_spec(spec, db, run_dir)
        finally:
            if db is not None:
                db.close()

    return _skip(spec, t0, f"{spec.mode} 模式暂不支持")


def main():
    ap = argparse.ArgumentParser(description="批量执行用例 → 汇总报告")
    ap.add_argument("--workspace", default=None, help="业务数据目录")
    ap.add_argument("--excel", default=None, help="固定格式 Excel 用例(自动草拟规格)")
    ap.add_argument("--sheet", default=None, help="Excel sheet 名(默认第一个)")
    ap.add_argument("--specs", default=None, help="已建模规格目录(*.yaml)")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条(0=全部)")
    ap.add_argument("--dry-run", action="store_true", help="只草拟/校验,不连库执行")
    ap.add_argument("--run-id", dest="run_id", default=None, help="运行标识(默认 run_时间戳)")
    ap.add_argument("--run-dir", dest="run_dir", default=None, help="运行目录(默认 <workspace>/runs/<run-id>)")
    ap.add_argument("--out", default=None, help="(已弃用)报告现固定输出到运行目录 report.html")
    args = ap.parse_args()

    if args.workspace:
        set_workspace(args.workspace)

    if args.excel:
        specs = [from_raw(c) for c in read_cases(args.excel, args.sheet)]
        print(f"[batch] 从 Excel 读入并草拟 {len(specs)} 条规格:{args.excel}")
    elif args.specs:
        specs = load_specs(args.specs)
        print(f"[batch] 载入已建模规格 {len(specs)} 条:{args.specs}")
    else:
        print("  ✗ 需指定 --excel 或 --specs"); sys.exit(2)

    if args.limit > 0:
        specs = specs[:args.limit]

    # 一次运行 = 一个文件夹:report.html + cases/<用例>/(截图/录像/数据)
    run_id = args.run_id or f"run_{time.strftime('%Y%m%d_%H%M%S')}"
    run_dir = Path(args.run_dir) if args.run_dir else (workspace_root() / "runs" / run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"[batch] 运行目录: {run_dir}")

    results = []
    for i, spec in enumerate(specs, 1):
        print(f"  [{i}/{len(specs)}] {spec.case_id} {spec.title[:40]} …", flush=True)
        results.append(execute(spec, args.dry_run, run_dir))

    reporter = Reporter()
    for r in results:
        reporter.add(r)
    print("\n" + reporter.render())

    report_path = run_report.render(run_id, results, run_dir)
    # 用例/数据/报告都在 run 文件夹里,自成一体
    print(f"\n  ✓ 报告: {report_path}")
    print(f"  ✓ 该次全部资料在: {run_dir}")


if __name__ == "__main__":
    main()
