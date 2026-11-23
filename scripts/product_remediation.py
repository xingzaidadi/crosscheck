"""Generate review-only remediation tasks and draft business assets."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.remediation_generator import generate_remediation_plan, write_draft_assets, write_remediation_plan  # noqa: E402
from core.suite_dsl import load_suite  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="生成前置状态和业务 Oracle 的审核草稿")
    parser.add_argument("--suite", required=True)
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--output")
    parser.add_argument("--draft-dir")
    args = parser.parse_args()
    suite, cases = load_suite(args.suite)
    plan = generate_remediation_plan(cases, suite_dir=args.suite, workspace=args.workspace)
    output = Path(args.output) if args.output else Path(args.suite) / "reports" / "remediation_plan.json"
    write_remediation_plan(plan, output)
    draft_dir = Path(args.draft_dir) if args.draft_dir else Path(args.suite) / "reports" / "remediation_drafts"
    paths = write_draft_assets(plan, draft_dir)
    print(json.dumps({"suite_id": suite["suite_id"], "plan": str(output),
                      "draft_dir": str(draft_dir), "task_count": plan["task_count"],
                      "draft_count": len(paths), "mode": plan["mode"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
