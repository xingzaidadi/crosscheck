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

try:  # Windows 控制台默认 GBK,强制 utf-8 才能打出 ✓ 和中文
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = REPO_ROOT / "templates"

SUBDIRS = [
    "config",
    "profiles",
    "knowledge_base/query_mapping",   # 查询类映射(probe 产草稿 → 人审)
    "knowledge_base/data_mapping",
    "knowledge_base/page_model",       # UI 录制蒸馏出的语义步骤
    "knowledge_base/field_intel",      # 自进化字段知识(越跑越熟)
    "specs_auto",                      # --auto-model 落盘的规格(待人审)
    "specs_write",                     # 手工/固化的写入规格
    "actions",
    "cases",                           # 用例 Excel
    "captures",                        # 抓包样本 / 提交体模板
    "artifacts",
    "runs",                            # 一次运行一个文件夹(report.html + 证据)
    "suites",                          # 套件级隔离:每套用例独立 cases/specs/captures/mappings
    ".auth",
]

# templates 里的样例 → workspace 里的落点
TEMPLATE_COPIES = [
    ("db.example.yaml", "config/db.example.yaml"),
    ("credentials.example.yaml", "config/credentials.example.yaml"),
    ("case_routes.example.yaml", "config/case_routes.example.yaml"),
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
    print("  接入新业务(零改框架码,详见 docs/ONBOARDING.md):")
    print(f"    1) config/db.yaml      ← 填库连接(cp db.example.yaml)")
    print(f"    2) profiles/<站点>.yaml ← 站点与登录(cp _example.yaml);run_verify login 建登录态")
    print(f"    3) config/case_routes.yaml ← 路由(cp case_routes.example.yaml);查询类先 run_verify probe 产映射并人审")
    print(f"    4) cases/ 放用例 Excel → python run_batch.py --excel <xlsx> --auto-model --workspace {target}")


if __name__ == "__main__":
    main()
