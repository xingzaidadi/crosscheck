"""
接入脚手架 验证:init_workspace 一条命令建出完整 workspace 骨架 + 模板。
守护"接入新业务零改框架码"的入口。离线。

跑:python tests/test_scaffold.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.init_workspace import init_workspace  # noqa: E402

EXPECT_DIRS = [
    "config", "profiles", "cases", "captures", "runs", "specs_auto", "specs_write",
    "knowledge_base/query_mapping", "knowledge_base/field_intel", "knowledge_base/page_model", ".auth",
]
EXPECT_TEMPLATES = [
    "config/db.example.yaml", "config/credentials.example.yaml",
    "config/case_routes.example.yaml", "profiles/_example.yaml",
]


def main():
    ws = Path(tempfile.mkdtemp()) / "biz"
    init_workspace(ws)
    print("接入脚手架 验证:\n")
    missing_d = [d for d in EXPECT_DIRS if not (ws / d).is_dir()]
    assert not missing_d, f"缺目录: {missing_d}"
    print(f"    ✓ 骨架目录齐全({len(EXPECT_DIRS)} 个,含 specs_auto/field_intel/page_model/runs)")
    missing_t = [t for t in EXPECT_TEMPLATES if not (ws / t).is_file()]
    assert not missing_t, f"缺模板: {missing_t}"
    print(f"    ✓ 配置模板齐全: {', '.join(Path(t).name for t in EXPECT_TEMPLATES)}")
    # 幂等:再建一次不报错、不覆盖
    init_workspace(ws)
    print("    ✓ 幂等:重复建不报错")
    print("\n全部通过 ✅  —— 接入新业务一条命令起骨架(零改框架码的入口)就位")


if __name__ == "__main__":
    main()
