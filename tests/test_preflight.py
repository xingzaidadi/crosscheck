"""Preflight 编排 验证(离线、零业务):注入假 sweeps,验 only 过滤 + 容错 + 能力图落盘。
跑:python tests/test_preflight.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from types import SimpleNamespace

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.workspace import set_workspace, kb_dir  # noqa: E402
from core.preflight import run_preflight  # noqa: E402


def main():
    print("Preflight 编排 验证:\n")
    set_workspace(tempfile.mkdtemp())

    prof = SimpleNamespace(site="demo", base_url="https://h/app", db_readonly="demo_db",
                           session_file="/nonexistent.json")
    sweeps = {
        "db": lambda p: {"ok": True, "source_path": "x.json", "detail": "3 表"},
        "api": lambda p: {"ok": True, "source_path": "y.json", "detail": "5 接口"},
        "site": lambda p: (_ for _ in ()).throw(RuntimeError("无登录态")),  # 故意抛
    }

    # only 过滤:只跑 db,api
    r = run_preflight(prof, only={"db", "api"}, sweeps=sweeps)
    assert set(r["steps"]) == {"db", "api"}, r
    assert r["steps"]["db"]["ok"] and r["steps"]["api"]["ok"]
    print("    ✓ --only 子集过滤(只跑 db,api)")

    # 全跑:site 抛异常 → 被捕成 ok:False,不中断
    r2 = run_preflight(prof, sweeps=sweeps)
    assert set(r2["steps"]) == {"db", "api", "site"}, r2
    assert r2["steps"]["site"]["ok"] is False and "异常" in r2["steps"]["site"]["missing"]
    assert r2["steps"]["db"]["ok"] is True
    print("    ✓ 单维度抛异常 → ok:False,其余照常")

    # 能力图落盘
    import json
    cap = json.loads((kb_dir() / "readiness" / "demo.json").read_text(encoding="utf-8"))
    assert cap["site"] == "demo" and "ts" in cap and set(cap["steps"]) == {"db", "api", "site"}
    print("    ✓ 能力图 readiness/demo.json 落盘")

    print("\n全部通过 ✅  —— Preflight 按序编排、容错、落能力图,零业务、离线可测")


if __name__ == "__main__":
    main()
