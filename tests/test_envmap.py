"""多步向导枚举 验证(离线、零业务):假选择树,验根→叶路径枚举 + 封顶。
跑:python tests/test_envmap.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.envmap import enumerate_paths  # noqa: E402


def main():
    print("多步向导枚举 验证:\n")

    # 树:org A 下有 scene a1/a2;org B 下只有 b1;scene 是叶子
    tree = {
        (): ["A", "B"],
        ("A",): ["a1", "a2"],
        ("B",): ["b1"],
        ("A", "a1"): [], ("A", "a2"): [], ("B", "b1"): [],
    }
    paths = enumerate_paths(lambda prefix: tree.get(tuple(prefix), []))
    assert sorted(paths) == [["A", "a1"], ["A", "a2"], ["B", "b1"]], paths
    print(f"    ✓ 枚举根→叶可达组合: {paths}")

    # 后一步依赖前面所选(B 下没有 a1)——已由上面体现
    assert ["B", "a1"] not in paths
    print("    ✓ 后续选项依赖前序选择(不产生非法组合)")

    # 封顶防爆:每步 3 选项、限 max_paths
    capped = enumerate_paths(lambda p: ["x", "y", "z"] if len(p) < 3 else [], max_paths=5)
    assert len(capped) == 5, len(capped)
    print(f"    ✓ max_paths 封顶: {len(capped)} 条")

    print("\n全部通过 ✅  —— 多步向导可达路径机器枚举,零业务离线可测")


if __name__ == "__main__":
    main()
