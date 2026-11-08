"""测试文件夹具生成(通用、零业务):上传/导入/大小限制类用例要现成文件(指定类型+大小)。
手工准备既繁琐又不可复现——fixtures 按需生成确定性文件(精确字节/行列),用完即弃。

零业务:类型与大小由调用方给;core 只负责"造出符合规格的文件"。
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def make_fixture(kind: str = "bin", *, size_bytes: int | None = None,
                 rows: int = 0, cols: int = 3, dir: str | None = None,
                 name: str | None = None) -> Path:
    """造一个夹具文件并返回路径。
      kind='bin' —— 精确 size_bytes 字节的二进制(大小限制类用)
      kind='txt' —— 文本;给 size_bytes 则填到该大小
      kind='csv' —— rows 行 × cols 列的 CSV
    文件落在 dir(默认临时目录),调用方用完自行删。"""
    d = Path(dir) if dir else Path(tempfile.mkdtemp())
    d.mkdir(parents=True, exist_ok=True)
    fn = name or f"fixture.{ 'csv' if kind == 'csv' else ('txt' if kind == 'txt' else 'bin') }"
    p = d / fn
    if kind == "csv":
        import csv
        with open(p, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow([f"col{i}" for i in range(cols)])
            for r in range(rows):
                w.writerow([f"r{r}c{c}" for c in range(cols)])
    elif kind == "txt":
        data = ("x" * size_bytes) if size_bytes is not None else "fixture\n"
        p.write_text(data, encoding="utf-8")
    else:  # bin
        n = size_bytes if size_bytes is not None else 1024
        with open(p, "wb") as f:
            f.write(b"\0" * n)
    return p


def make_oversize(limit_bytes: int, *, kind: str = "bin", over: int = 1, dir: str | None = None) -> Path:
    """造一个刚好超过 limit_bytes 的文件(大小上限的负向用例:应被拒)。"""
    return make_fixture(kind, size_bytes=limit_bytes + over, dir=dir, name="oversize.bin")


def make_undersize(limit_bytes: int, *, kind: str = "bin", under: int = 1, dir: str | None = None) -> Path:
    """造一个刚好不超过 limit_bytes 的文件(边界正向:应通过)。"""
    return make_fixture(kind, size_bytes=max(0, limit_bytes - under), dir=dir, name="undersize.bin")


def file_size(p: str | Path) -> int:
    return os.path.getsize(p)
