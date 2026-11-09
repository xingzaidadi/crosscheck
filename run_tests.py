"""统一自测:一条命令跑完 tests/ 下全部离线单测(含零业务门禁),出汇总 + 退出码。
全部离线、零真实环境依赖。跑:python run_tests.py
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent


def main() -> int:
    tests = sorted((ROOT / "tests").glob("test_*.py"))
    print(f"统一自测:{len(tests)} 个用例(离线)\n")
    passed, failed = [], []
    t0 = time.time()
    for t in tests:
        r = subprocess.run([sys.executable, "-I", str(t)], cwd=str(ROOT),
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
