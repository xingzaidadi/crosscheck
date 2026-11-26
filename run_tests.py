"""统一自测:一条命令跑完 tests/ 下全部离线单测(含零业务门禁),出汇总 + 退出码。
全部离线、零真实环境依赖。跑:python run_tests.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import argparse
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent


def _subprocess_env() -> dict:
    """子进程环境:把仓库根注入 PYTHONPATH,保证 import core/adapters/db/scripts 可解析。

    历史上这里用 python -I(隔离模式),它会清空 PYTHONPATH 且不读 pytest.ini 的
    pythonpath,导致所有 import core 的用例误报 ModuleNotFoundError。统一走显式 env。"""
    environment = dict(os.environ)
    environment["PYTHONUTF8"] = "1"
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        os.pathsep.join([str(ROOT), existing]) if existing else str(ROOT)
    )
    return environment



def main() -> int:
    parser = argparse.ArgumentParser(description="运行 tests/ 下全部离线回归")
    parser.add_argument("--coverage", action="store_true", help="用 coverage 子进程统计测试覆盖率")
    args = parser.parse_args()
    tests = sorted((ROOT / "tests").glob("test_*.py"))
    print(f"统一自测:{len(tests)} 个用例(离线)\n")
    passed, failed = [], []
    t0 = time.time()
    environment = _subprocess_env()
    for t in tests:
        command = [sys.executable, str(t)]
        if args.coverage:
            command = [sys.executable, "-m", "coverage", "run", "--parallel-mode",
                       "--source=core,adapters,db,scripts", str(t)]
        r = subprocess.run(command, cwd=str(ROOT), env=environment,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        ok = r.returncode == 0
        (passed if ok else failed).append(t.name)
        if not ok:
            tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
            print(f"  ✗ {t.name}")
            for ln in tail:
                print(f"      {ln}")
    dt = round(time.time() - t0, 1)
    print(f"\n小结:共 {len(tests)} · 通过 {len(passed)} · 失败 {len(failed)} · {dt}s")
    if failed:
        print("失败:", failed)
    # 零业务门禁必须在通过之列(双保险)
    guard_ok = "test_no_business_in_core.py" in passed
    print(f"零业务门禁:{'✓ 通过' if guard_ok else '✗ 未通过/缺失'}")
    return 0 if (not failed and guard_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
