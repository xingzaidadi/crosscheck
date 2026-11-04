"""
建一个空的 workspace 骨架 —— 别人装完框架后,一条命令就能起自己的业务目录。

  python scripts/init_workspace.py <目标目录>

产出 <目标目录>/:
  config/        db.example.yaml、credentials.example.yaml(从 templates 拷入,复制为去 .example 的真名后填值)
  profiles/      _example.yaml(新站点模板)
  knowledge_base/{query_mapping,data_mapping,page_model}
  actions/ cases/ captures/ artifacts/ .auth/

建好后让框架用它:--workspace <目标目录>,或设 VTA_WORKSPACE,或把它命名为 ./workspace。
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = REPO_ROOT / "templates"

SUBDIRS = [
    "config",
    "profiles",
    "knowledge_base/query_mapping",
    "knowledge_base/data_mapping",
    "knowledge_base/page_model",
    "actions",
    "cases",
    "captures",
    "artifacts",
    ".auth",
]

# templates 里的样例 → workspace 里的落点
TEMPLATE_COPIES = [
    ("db.example.yaml", "config/db.example.yaml"),
    ("credentials.example.yaml", "config/credentials.example.yaml"),
    ("profile.example.yaml", "profiles/_example.yaml"),
]


def init_workspace(target: Path) -> None:
    for sub in SUBDIRS:
        (target / sub).mkdir(parents=True, exist_ok=True)
    for src_name, dst_rel in TEMPLATE_COPIES:
        src = TEMPLATES / src_name
        dst = target / dst_rel
        if src.exists() and not dst.exists():
            shutil.copyfile(src, dst)


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    target = Path(sys.argv[1]).resolve()
    init_workspace(target)
    print(f"✓ workspace 骨架已建好: {target}")
    print("  下一步:")
    print(f"    1) cp {target / 'config' / 'db.example.yaml'} {target / 'config' / 'db.yaml'}  并填真实连接")
    print(f"    2) 按 {target / 'profiles' / '_example.yaml'} 写一个 profiles/<你的站点>.yaml")
    print(f"    3) python run_record.py --profile <你的站点> --workspace {target}")


if __name__ == "__main__":
    main()
