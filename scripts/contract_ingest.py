"""crosscheck contract-ingest —— 从源码或 API 文档摄取接口契约,产出 ExecSpec 草稿 + 负例草稿。

薄驱动:解析、规范化、草稿生成的通用机制都在 core.contract_ingest(零业务)。
本脚本只负责 CLI 参数与落盘到 workspace 知识库。

用法:
  # 有后端源码(Java/Spring)
  python scripts/contract_ingest.py java_spring <源码根> --context demand --site ebuy-demand --workspace workspace
  # 无源码,有 OpenAPI/Swagger 文档
  python scripts/contract_ingest.py openapi <openapi.json> --site my-system --workspace workspace
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import contract_ingest as ci  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="摄取接口契约并生成 ExecSpec/负例草稿")
    parser.add_argument("provider", choices=ci.providers())
    parser.add_argument("source", help="源码根(java_spring)或文档路径(openapi)")
    parser.add_argument("--context", default="", help="服务上下文前缀(java_spring 用)")
    parser.add_argument("--site", default="")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--output")
    args = parser.parse_args()

    contract = ci.ingest(args.provider, args.source, site=args.site, context=args.context)
    drafts = ci.contract_to_drafts(contract)
    site = contract.site

    ws = Path(args.workspace)
    contract_path = ws / "knowledge_base" / "contracts" / f"{site}.json"
    drafts_path = Path(args.output) if args.output else \
        ws / "knowledge_base" / "contract_drafts" / f"{site}.json"
    for p in (contract_path, drafts_path):
        p.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text(json.dumps(contract.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    drafts_path.write_text(json.dumps(drafts, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"契约摄取({args.provider}):{drafts['endpoint_count']} 端点,"
          f"{drafts['negative_count']} 条负例草稿")
    print(f"  契约 → {contract_path}")
    print(f"  草稿 → {drafts_path}")
    print("  草稿为 verify_status=draft,人审或经 modeler 补 oracle 后才进执行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
