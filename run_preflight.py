"""
入口:Preflight 环境自发现。人只给一个 Site Profile(或先 run_bootstrap 自动生成它)。

  python run_preflight.py <site> [--only db,api,site] [--workspace <dir>]

把现有发现库跑成一趟:
  db   —— 库结构 + 状态字段真实取值      → knowledge_base/schema_map/<db>.json
  api  —— 历史流量聚合成接口目录          → knowledge_base/api_catalog/<site>.json
  site —— 爬页面 + 抓接口 + 请求体样本     → knowledge_base/sitemap/<site>.json
汇总能力就绪图 → knowledge_base/readiness/<site>.json。

db/api 无需浏览器;site 需登录态(先 run_verify.py login --profile <site> 或 run_bootstrap)。
各维度独立容错,一个失败不拖垮其余。
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

from core.preflight import run_preflight  # noqa: E402
from core.profile import load_profile, list_profiles  # noqa: E402
from core.workspace import set_workspace  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Preflight 环境自发现编排器")
    ap.add_argument("site", help="Site Profile 名(profiles/<site>.yaml)")
    ap.add_argument("--only", default="", help="只跑子集,逗号分隔: db,api,site")
    ap.add_argument("--workspace", default="", help="workspace 根目录(默认 ./workspace)")
    args = ap.parse_args(argv)

    if args.workspace:
        set_workspace(args.workspace)

    try:
        profile = load_profile(args.site)
    except FileNotFoundError as e:
        print(f"[错误] {e}")
        print(f"现有 profile: {list_profiles()}")
        return 2

    only = {s.strip() for s in args.only.split(",") if s.strip()} or None
    print(f"Preflight 自发现: site={profile.site} base_url={profile.base_url or '(未配)'}"
          f"{' only=' + ','.join(sorted(only)) if only else ''}\n")

    result = run_preflight(profile, only=only)

    ok = 0
    for dim, st in result["steps"].items():
        mark = "[✓]" if st.get("ok") else "[×]"
        detail = st.get("detail") or st.get("missing") or ""
        src = st.get("source_path", "")
        print(f"  {mark} {dim:5s}  {detail}")
        if src:
            print(f"        → {src}")
        ok += 1 if st.get("ok") else 0
    print(f"\n小结: {ok}/{len(result['steps'])} 维度就绪 · 能力图 → knowledge_base/readiness/{profile.site}.json")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
