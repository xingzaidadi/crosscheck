"""scorecard._read_demo 认 demo-result.json:local_demo.py 的真实产物位置。

回归锁:local_demo.py 产 <ws>/demo-result.json(passed=True 三源),而历史
_read_demo 只扫 <ws>/runs/*/summary.json——真打通却读不到,e2e_demo 恒 0。
本测确保两种位置都被识别,且 passed!=True 不误判打通。
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:  # 单独运行时也能打印 ✓(run_tests.py 已以 utf-8 跑子进程)
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from scripts.scorecard import _read_demo  # noqa: E402


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_reads_demo_result_json():
    # local_demo.py 的真实产物:<ws>/demo-result.json,三源打通 passed=True。
    with tempfile.TemporaryDirectory() as d:
        ws = Path(d)
        _write(ws / "demo-result.json", {
            "passed": True,
            "ui": {"screenshot": "x.png"},
            "api": {"status": 201},
            "db": {"row": [1, "X"], "residue": 0},
        })
        assert _read_demo(str(ws), run_demo=False) is True
    print("  ✓ 认 <ws>/demo-result.json 的 passed=True(local_demo 真实产物)")


def test_reads_runs_summary_json():
    # 历史编排产物:<ws>/runs/<id>/summary.json。
    with tempfile.TemporaryDirectory() as d:
        ws = Path(d)
        _write(ws / "runs" / "r1" / "summary.json", {"passed": True})
        assert _read_demo(str(ws), run_demo=False) is True
    print("  ✓ 认 <ws>/runs/*/summary.json 的 passed=True(历史位置不回退)")


def test_not_passed_is_not_through():
    # UI 单层探索 passed=None/False 不算三源打通。
    with tempfile.TemporaryDirectory() as d:
        ws = Path(d)
        _write(ws / "demo-result.json", {"passed": None})
        _write(ws / "runs" / "r1" / "summary.json", {"passed": False})
        assert _read_demo(str(ws), run_demo=False) is False
    print("  ✓ passed 非 True 不误判打通(宁缺毋滥)")


def test_missing_workspace_is_false():
    assert _read_demo(None, run_demo=False) is False
    assert _read_demo(str(ROOT / "_definitely_absent_ws"), run_demo=False) is False
    print("  ✓ 无 demo workspace / 不存在目录返回 False")


def main():
    test_reads_demo_result_json()
    test_reads_runs_summary_json()
    test_not_passed_is_not_through()
    test_missing_workspace_is_false()
    print("\n全部通过 ✅  —— _read_demo 认 demo-result.json 与 runs/summary.json 两种位置")


if __name__ == "__main__":
    main()
