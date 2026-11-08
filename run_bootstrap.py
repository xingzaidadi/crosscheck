"""
入口:极简自举。给一个 URL,浏览器登一次,工具自动识别并写好 Site Profile——用户不写 yaml。

  python run_bootstrap.py <url> [--roles demander,acceptor] [--db <db名>] [--workspace <dir>]

流程:解析 site/base_url → 开浏览器识别 UI 套件 → 每个角色弹浏览器登一次(人正常登,SSO/2FA 都行)
     → 生成 workspace/profiles/<site>.yaml + workspace/accounts/<site>.yaml。
随后:run_preflight.py <site> 自发现环境,再喂用例跑。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.bootstrap import bootstrap  # noqa: E402
from core.workspace import set_workspace  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="极简自举:URL → 自动生成 Site Profile")
    ap.add_argument("url", help="系统任意一个页面 URL")
    ap.add_argument("--roles", default="default", help="角色键,逗号分隔(每个登一次);默认 default")
    ap.add_argument("--db", default="", help="只读库名(可选,填了才做库层校验;不填只页面+接口两源)")
    ap.add_argument("--workspace", default="", help="workspace 根目录(默认 ./workspace)")
    args = ap.parse_args(argv)

    if args.workspace:
        set_workspace(args.workspace)

    roles = [r.strip() for r in args.roles.split(",") if r.strip()] or ["default"]
    print(f"自举: {args.url}\n  角色: {roles}  {'库=' + args.db if args.db else '(无库,页面+接口两源)'}\n")
    print("  即将为每个角色弹出浏览器,请在其中正常登录(含 SSO/2FA),登完工具自动保存登录态。\n")

    res = bootstrap(args.url, roles=roles, db_readonly=(args.db or None))

    kit = res["ui_kit"]
    print(f"\n  站点: {res['site']}  base_url: {res['base_url']}")
    print(f"  UI 套件: {kit['kit']}(置信度 {kit['confidence']})")
    print(f"  Profile → {res['profile_path']}")
    print(f"  账号表 → {res['accounts_path']}")
    print(f"\n下一步: python run_preflight.py {res['site']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
