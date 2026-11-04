"""
录制 + 报告 一体化。开浏览器(全程录视频 + 关键步骤截图)→ 确保登录 → 操作检索
→ 抓接口 → 自动建模草稿 →(若已有审过的映射则)连库对账 → 出 HTML 报告。

  python run_record.py --profile <your-site>                              # 用 profile.defaults 的页面/库
  python run_record.py --profile <your-site> --actions <workspace>/actions/<x>.json  # 声明式驱动检索
  python run_record.py --profile <your-site> --relogin                    # 强制重登

产出 artifacts/<feature>_<ts>/:video.webm、NN_*.png、picked.json、mapping.draft.json、report.html
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

from core.prober import Prober  # noqa: E402
from core.mapping_builder import build_mapping_draft  # noqa: E402
from core.reconciler import Reconciler  # noqa: E402
from core.report import build_report  # noqa: E402
from core.profile import load_profile  # noqa: E402
from core.login import ensure_session  # noqa: E402
from core.config import site_credentials  # noqa: E402
from core.workspace import set_workspace, artifacts_dir, auth_dir, kb_dir  # noqa: E402
from db.client import DbClient  # noqa: E402


def _open_db(profile):
    from core.config import db_params
    p = db_params(profile.db_readonly) if profile.db_readonly else None
    return DbClient(readonly_params=p) if p else None


def main():
    ap = argparse.ArgumentParser(description="录制 + 报告 一体化跑测")
    ap.add_argument("--profile", required=True)
    ap.add_argument("--actions", default=None, help="声明式检索动作 JSON(选组织/场景/点查询)")
    ap.add_argument("--relogin", action="store_true")
    ap.add_argument("--wait", type=int, default=5000)
    ap.add_argument("--no-login", action="store_true", help="跳过登录(复用已有 session,调试用)")
    ap.add_argument("--launch-mode", default=None,
                    choices=["persistent", "existing", "isolated"],
                    help="开浏览器方式:persistent(真Chrome+持久profile,默认) / existing(连已开浏览器,配 --cdp) / isolated(干净Chromium)")
    ap.add_argument("--cdp", default=None, help="existing 模式的 CDP 地址,如 http://127.0.0.1:9222")
    ap.add_argument("--workspace", default=None, help="业务数据目录(省略则按 VTA_WORKSPACE / ./workspace / 仓库根 解析)")
    args = ap.parse_args()

    if args.workspace:
        set_workspace(args.workspace)

    profile = load_profile(args.profile)
    feature = profile.defaults.get("feature", profile.site)
    page_url = profile.defaults.get("probe_url") or profile.base_url
    rundir = artifacts_dir() / f"{feature}_{int(time.time())}"
    rundir.mkdir(parents=True, exist_ok=True)
    print(f"[run] 站点 {profile.site} · 功能 {feature}\n  产出目录: {rundir}")

    # 1) 登录态
    if not args.no_login:
        print(f"[login] 模式 {profile.login.mode}")
        ensure_session(profile, site_credentials(profile.site), force=args.relogin)

    # 2) 声明式检索动作(可选)
    actions = None
    if args.actions:
        actions = json.loads(Path(args.actions).read_text(encoding="utf-8"))
        print(f"[actions] 载入 {len(actions)} 步检索动作")

    # 3) 录制 + 抓包
    launch_mode = args.launch_mode or profile.defaults.get("launch_mode", "persistent")
    udd = str(auth_dir() / f"{profile.site}_profile")
    print(f"[record] 开浏览器({launch_mode}),录视频 + 截图 + 抓接口…")
    prober = Prober(
        url_pattern=profile.defaults.get("url_pattern", "") or "",
        session_file=profile.session_file,
        headless=False,
        video_dir=str(rundir),
        artifacts_dir=str(rundir),
        launch_mode=launch_mode,
        user_data_dir=udd,
        cdp_endpoint=args.cdp,
    )
    prober.probe(page_url, wait_ms=args.wait, actions=actions, record=not actions)
    print(f"  抓到 {len(prober.captures)} 次调用,截图 {len(prober.screenshots)} 张,"
          f"视频 {'有' if prober.video_path else '无'}")

    picked = prober.pick_search_call()
    picked_dict = picked.__dict__ if picked else None
    if picked:
        (rundir / "picked.json").write_text(
            json.dumps(picked_dict, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  认出检索接口: {picked.method} {picked.url}")
    else:
        print("  未认出检索接口(可能检索未触发/返回非列表);视频截图仍会入报告。")

    # 4) 自动建模草稿 + (有审过映射才)对账
    reconcile_text = None
    consistent = None
    table = profile.defaults.get("table", "")
    db = None
    try:
        db = _open_db(profile)
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ 连库失败: {e}")

    if picked and db and table:
        cols = db.columns(table)
        draft = build_mapping_draft(picked, db_name=profile.defaults.get("db", ""),
                                    table=table, pk=profile.defaults.get("pk", "id"), columns=cols)
        draft["feature"] = feature
        (rundir / "mapping.draft.json").write_text(
            json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  映射草稿已生成(表 {table},{len(cols)} 列)→ {rundir/'mapping.draft.json'}")

        approved = kb_dir() / "query_mapping" / f"{feature}.json"
        if approved.exists():
            mapping = json.loads(approved.read_text(encoding="utf-8"))
            api_params = picked_dict.get("request_body") or picked_dict.get("query_params") or {}
            api_resp = picked_dict.get("response_json") or {}
            result = Reconciler(db, mapping).reconcile(api_params, api_resp)
            reconcile_text = result.render()
            consistent = result.consistent
            print("  已用审过的映射对账。")
        else:
            print(f"  (尚无审过的映射 {approved.name},本次只出草稿,不对账)")
    if db:
        db.close()

    # 5) 报告
    report = build_report(
        rundir / "report.html",
        feature=feature, site=profile.site, page_url=page_url,
        picked=picked_dict, reconcile_text=reconcile_text, consistent=consistent,
        screenshots=prober.screenshots, video_path=prober.video_path,
        capture_count=len(prober.captures),
    )
    print(f"\n  ✓ 报告: {report}")


if __name__ == "__main__":
    main()
