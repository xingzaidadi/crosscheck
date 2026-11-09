"""一键编排入口:给新手的"一条命令跑完"。

  python run_crosscheck.py --workspace workspace

默认行为(零记忆负担):
  1. 自动找 workspace/cases 下最新的 .xlsx 用例;
  2. 对本批站点检活/续期(--ensure-login);
  3. 自动建模(复用路由+映射+抓包)并合并人审 UI 规格(workspace/specs_ui_valid)——
     一跑覆盖 接口 + UI + 自定义;
  4. 跑 workspace/checks/*.py 里的自定义不变式检查(可选,有就跑);
  5. 刷新 142 条终态清单(manifest),出统一小结 + 报告路径。

只编排、不含业务;换系统改 workspace 即可。--preflight <profile> 可在跑前先做自发现体检。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent


def _latest_excel(ws: Path) -> str | None:
    xs = sorted((ws / "cases").glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(xs[0]) if xs else None


def _run(cmd: list[str]) -> int:
    print(f"\n$ {' '.join(cmd)}\n", flush=True)
    return subprocess.run(cmd, cwd=str(ROOT)).returncode


def main():
    ap = argparse.ArgumentParser(description="一键编排:检活→自动建模(接口+UI)→自定义检查→清单+报告")
    ap.add_argument("--workspace", default="workspace", help="业务数据目录")
    ap.add_argument("--excel", default=None, help="用例 Excel(默认取 workspace/cases 最新一份)")
    ap.add_argument("--with-specs", dest="with_specs", default=None,
                    help="额外人审规格目录(默认 workspace/specs_verified 若存在)")
    ap.add_argument("--preflight", default=None, help="跑前先对该 profile 做自发现体检(可选)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default=None)
    ap.add_argument("--no-login", dest="no_login", action="store_true", help="跳过检活续期")
    ap.add_argument("--run-id", dest="run_id", default=None)
    args = ap.parse_args()

    ws = Path(args.workspace)
    if not ws.exists():
        print(f"  ✗ workspace 不存在:{ws}"); sys.exit(2)
    excel = args.excel or _latest_excel(ws)
    if not excel:
        print(f"  ✗ 未找到用例 Excel(放 {ws}/cases/*.xlsx 或用 --excel 指定)"); sys.exit(2)
    with_specs = args.with_specs or (str(ws / "specs_verified") if (ws / "specs_verified").exists() else None)
    run_id = args.run_id or f"run_{time.strftime('%Y%m%d_%H%M%S')}"
    py = sys.executable

    print("=" * 60)
    print(f"crosscheck 一键编排  ·  workspace={ws}  ·  run_id={run_id}")
    print(f"  用例: {excel}")
    print(f"  合并规格: {with_specs or '—'}   自定义检查: {ws / 'checks'}")
    print("=" * 60)

    # 1) 可选:跑前自发现体检
    if args.preflight:
        _run([py, "-I", "run_preflight.py", "--workspace", str(ws), "--profile", args.preflight])

    # 2) 主套:自动建模 + 合并 UI 规格 + 检活
    cmd = [py, "-I", "run_batch.py", "--workspace", str(ws), "--excel", excel,
           "--auto-model", "--run-id", run_id]
    if with_specs:
        cmd += ["--with-specs", with_specs]
    if not args.no_login:
        cmd += ["--ensure-login"]
    if args.limit:
        cmd += ["--limit", str(args.limit)]
    if args.only:
        cmd += ["--only", args.only]
    rc = _run(cmd)

    # 3) 自定义不变式检查(workspace/checks/*.py):有就逐个跑,汇总 pass/fail
    checks_dir = ws / "checks"
    extra = {"ran": 0, "pass": 0, "fail": 0, "detail": []}
    if checks_dir.exists():
        for chk in sorted(checks_dir.glob("*.py")):
            r = subprocess.run([py, "-I", str(chk)], cwd=str(ROOT), capture_output=True, text=True)
            ok = r.returncode == 0
            extra["ran"] += 1; extra["pass" if ok else "fail"] += 1
            extra["detail"].append({"check": chk.name, "ok": ok, "tail": (r.stdout or r.stderr).strip().splitlines()[-1:] })
            print(f"  [检查] {chk.name}: {'通过' if ok else '失败'}")

    # 4) 刷新终态清单(142 条全覆盖账)
    mf = ws / "scripts" / "run_manifest.py"
    if mf.exists():
        _run([py, "-I", str(mf)])

    # 5) 统一小结
    print("\n" + "=" * 60)
    print("一键编排完成")
    rp = ws / "runs" / run_id / "report.html"
    if rp.exists():
        print(f"  ✓ 本次报告: {rp}")
    if extra["ran"]:
        print(f"  ✓ 自定义检查: 共 {extra['ran']} · 通过 {extra['pass']} · 失败 {extra['fail']}")
    print(f"  主套退出码: {rc}")
    print("=" * 60)
    sys.exit(0 if rc == 0 else 1)


if __name__ == "__main__":
    main()
