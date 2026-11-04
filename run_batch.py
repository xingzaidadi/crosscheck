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

from core.workspace import set_workspace, kb_dir, captures_dir  # noqa: E402
from core.case_source import read_cases  # noqa: E402
from core.spec import ExecSpec, from_raw, load_specs  # noqa: E402
from core.reporter import Reporter  # noqa: E402
from core.interfaces import CaseResult, Verdict  # noqa: E402
from core.reconciler import Reconciler  # noqa: E402
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


def _run_reconcile(spec: ExecSpec) -> tuple[Verdict, list[str]]:
    feature = spec.feature or spec.case_id
    mapping_path = Path(spec.mapping) if spec.mapping else kb_dir() / "query_mapping" / f"{feature}.json"
    sample_path = Path(spec.sample) if spec.sample else captures_dir() / f"{feature}_picked.json"
    if not mapping_path.exists():
        return Verdict.SKIP, [f"未建模:缺映射 {mapping_path.name}(先 run_verify probe + 人审)"]
    if not sample_path.exists():
        return Verdict.SKIP, [f"缺抓包样本 {sample_path.name}(先 run_verify probe)"]
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    picked = json.loads(sample_path.read_text(encoding="utf-8"))
    api_params = picked.get("request_body") or picked.get("query_params") or {}
    api_resp = picked.get("response_json") or {}
    db = _open_db(spec.db)
    if db is None:
        return Verdict.ENV_ERROR, ["未配可用只读库(workspace/config/db.yaml),无法对账"]
    try:
        res = Reconciler(db, mapping).reconcile(api_params, api_resp)
    finally:
        db.close()
    return (Verdict.PASS, ["对账一致"]) if res.consistent else (Verdict.FAIL, res.render().splitlines())


def execute(spec: ExecSpec, dry_run: bool) -> CaseResult:
    t0 = time.time()
    verdict, details = Verdict.SKIP, []
    if dry_run:
        details = [f"dry-run:仅草拟/校验(kind={spec.kind}, mode={spec.mode}, 接口={spec.endpoints or '—'})"]
    elif spec.verify_status != "human_verified":
        details = ["未人审(draft):补全 assertions / feature 并转 human_verified 后再执行"]
    elif spec.mode == "reconcile":
        verdict, details = _run_reconcile(spec)
    else:
        details = [f"{spec.mode} 模式(写入/UI)待 Phase 2 实现"]
    return CaseResult(
        case_id=spec.case_id, verdict=verdict, details=details,
        duration_s=round(time.time() - t0, 3),
        title=spec.title, kind=spec.kind, mode=spec.mode,
    )


def main():
    ap = argparse.ArgumentParser(description="批量执行用例 → 汇总报告")
    ap.add_argument("--workspace", default=None, help="业务数据目录")
    ap.add_argument("--excel", default=None, help="固定格式 Excel 用例(自动草拟规格)")
    ap.add_argument("--sheet", default=None, help="Excel sheet 名(默认第一个)")
    ap.add_argument("--specs", default=None, help="已建模规格目录(*.yaml)")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条(0=全部)")
    ap.add_argument("--dry-run", action="store_true", help="只草拟/校验,不连库执行")
    ap.add_argument("--out", default=None, help="HTML 报告输出路径")
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

    reporter = Reporter()
    for i, spec in enumerate(specs, 1):
        print(f"  [{i}/{len(specs)}] {spec.case_id} {spec.title[:40]} …", flush=True)
        reporter.add(execute(spec, args.dry_run))

    print("\n" + reporter.render())
    if args.out:
        p = reporter.to_html(args.out)
        print(f"\n  ✓ HTML 报告: {p}")


if __name__ == "__main__":
    main()
