"""
入口:接入一个新站点时,先扫一遍能查到的,把查不到的列成"缺口",交给交互层按清单主动追问。
人只给一个 URL(可选再给代码库路径、库名),工具自己跑 bootstrap/sitemap/dbmap/srcmap,
产出 gap_report —— 用户不必自己想该给什么、也不必手写一堆 yaml。

  python run_onboard.py scan --url "<站点URL>" [--code-path <后端代码库>] [--db <库名>] \
      [--site <站点键>] [--session <登录态json>] [--workspace <ws>] [--no-write]

产出(默认落在 <workspace>/onboard/<site>_gap_report.json):
  known  —— 扫到的:站点/登录方式候选/页面目录/库表/源码契约
  have   —— workspace 里各槽位是否已配
  gaps   —— 还该问用户的槽位(带扫到的候选当选择题提示)

接下来由 `crosscheck-onboard` 技能读 gap_report、按清单逐项追问、生成配置,再交给 crosscheck 跑。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.onboard import scan_all  # noqa: E402
from core.workspace import set_workspace  # noqa: E402


def cmd_scan(args: argparse.Namespace) -> int:
    report = scan_all(
        args.url, site=args.site, code_path=args.code_path, db_name=args.db,
        context=args.context or "", session_file=args.session,
        write=not args.no_write,
    )
    known, gaps = report["known"], report["gaps"]
    print(f"\n=== 接入扫描:{known.get('site')}  ({known.get('base_url')}) ===")
    print(f"  登录方式候选 : {known['login'].get('method')}  信号={known['login'].get('signals')}"
          + ("  +代登框" if known['login'].get('act_as_candidate') else ""))
    print(f"  页面目录     : {len(known.get('pages') or [])} 页 / {known.get('api_count')} 接口")
    print(f"  库表         : {len(known.get('tables') or {})} 张")
    print(f"  源码契约     : {len(known.get('contracts') or [])} 个端点")
    if known.get("scan_errors"):
        print(f"  ⚠ 部分未扫到 : {known['scan_errors']}")
    print(f"\n  缺口 {len(gaps)} 项(交互层按此逐项追问):")
    for g in gaps:
        hint = f"   · 扫到:{g['scan_hint']}" if g.get("scan_hint") else ""
        print(f"    - [{g['slot']}] {g['ask']}{hint}")
    if report.get("report_path"):
        print(f"\n  ✓ gap_report: {report['report_path']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="接入扫描:扫一遍 → 产缺口报告")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("scan", help="扫站点/库/代码库,产 gap_report")
    sc.add_argument("--url", required=True, help="站点根 URL(带登录态更全)")
    sc.add_argument("--site", default=None, help="站点键(省略则从 URL 主机名推)")
    sc.add_argument("--code-path", default=None, help="后端代码库路径(可选,给了就读契约)")
    sc.add_argument("--db", default=None, help="db.yaml 里的库名(给了就扫 schema)")
    sc.add_argument("--context", default="", help="源码上下文前缀(Spring context-path)")
    sc.add_argument("--session", default=None, help="登录态 json(爬页用)")
    sc.add_argument("--workspace", default=None, help="workspace 根")
    sc.add_argument("--no-write", action="store_true", help="只打印,不落 gap_report.json")
    sc.set_defaults(func=cmd_scan)

    args = ap.parse_args()
    if args.workspace:
        set_workspace(args.workspace)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
