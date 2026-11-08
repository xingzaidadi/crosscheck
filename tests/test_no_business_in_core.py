"""零业务门禁(通用性红线的自动守卫):core/ 里不得出现任何业务词。
业务事实全落 workspace/;core 只放机制。换业务只改 tests/fixtures/business_terms.txt。

跑:python tests/test_no_business_in_core.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _load_terms() -> list[str]:
    p = os.path.join(ROOT, "tests", "fixtures", "business_terms.txt")
    terms = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s and not s.startswith("#"):
                terms.append(s)
    return terms


def _scan(core_dir: str, terms: list[str]) -> list[tuple[str, int, str, str]]:
    hits = []
    for dirpath, _dirs, files in os.walk(core_dir):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            fp = os.path.join(dirpath, fn)
            try:
                lines = open(fp, encoding="utf-8").read().splitlines()
            except Exception:  # noqa: BLE001
                continue
            for i, line in enumerate(lines, 1):
                for t in terms:
                    if t in line:
                        rel = os.path.relpath(fp, ROOT).replace("\\", "/")
                        hits.append((rel, i, t, line.strip()[:80]))
    return hits


def main():
    print("零业务门禁:扫描 core/ 是否残留业务词\n")
    terms = _load_terms()
    print(f"    业务词清单 {len(terms)} 个: {terms}")
    hits = _scan(os.path.join(ROOT, "core"), terms)
    if hits:
        print(f"\n    ✗ 发现 {len(hits)} 处业务污染:")
        for rel, ln, t, snip in hits:
            print(f"      {rel}:{ln}  [{t}]  {snip}")
        raise AssertionError(f"core/ 残留 {len(hits)} 处业务词,违反零业务红线")
    print("\n全部通过 ✅  —— core/ 零业务,换业务不改框架码")


if __name__ == "__main__":
    main()
