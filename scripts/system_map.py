from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.system_map import write_system_map  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 UI/API/DB/状态/知识统一系统地图")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--output")
    args = parser.parse_args()
    print(write_system_map(args.workspace, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
