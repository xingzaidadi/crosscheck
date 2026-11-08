"""测试文件夹具 验证(离线、零业务):精确大小/类型 + 上限负向/正向边界。
跑:python tests/test_fixtures.py
"""
from __future__ import annotations

import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.fixtures import make_fixture, make_oversize, make_undersize, file_size  # noqa: E402


def main():
    print("测试文件夹具 验证:\n")
    d = tempfile.mkdtemp()

    b = make_fixture("bin", size_bytes=2048, dir=d)
    assert file_size(b) == 2048
    print("    ✓ bin 精确字节")

    c = make_fixture("csv", rows=3, cols=2, dir=d)
    lines = open(c, encoding="utf-8").read().splitlines()
    assert lines[0] == "col0,col1" and len(lines) == 4
    print("    ✓ csv 行列")

    limit = 100 * 1024
    over = make_oversize(limit, dir=d)
    under = make_undersize(limit, dir=d)
    assert file_size(over) == limit + 1 and file_size(under) == limit - 1
    print(f"    ✓ 上限边界: over={file_size(over)} > {limit} > under={file_size(under)}")

    print("\n全部通过 ✅  —— 夹具按规格确定性生成,零业务离线可测")


if __name__ == "__main__":
    main()
