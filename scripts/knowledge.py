"""Manage workspace knowledge without exposing workspace secrets."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.knowledge import KnowledgeBase  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="查询、记录和审批 Crosscheck 项目知识")
    parser.add_argument("--workspace", default="workspace")
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="搜索已批准知识")
    search.add_argument("query")

    record = sub.add_parser("record-answer", help="把用户回答记录为待审批知识")
    record.add_argument("--question", required=True)
    record.add_argument("--answer", required=True)
    record.add_argument("--project", default="")
    record.add_argument("--module", default="")
    record.add_argument("--feature", default="")
    record.add_argument("--type", default="business_rule")

    approve = sub.add_parser("approve", help="审批一条候选知识")
    approve.add_argument("knowledge_id")
    approve.add_argument("--approver", default="human")

    check = sub.add_parser("check-question", help="提问前检查是否已有可强制复用的答案")
    check.add_argument("--question", required=True)
    check.add_argument("--project", default="")
    check.add_argument("--module", default="")
    check.add_argument("--feature", default="")

    stale = sub.add_parser("mark-stale", help="标记知识过期")
    stale.add_argument("knowledge_id")
    stale.add_argument("--reason", required=True)

    supersede = sub.add_parser("supersede", help="用新知识替代旧知识")
    supersede.add_argument("old_id")
    supersede.add_argument("new_id")
    supersede.add_argument("--approver", default="human")

    sub.add_parser("conflicts", help="列出知识冲突")

    recommend = sub.add_parser("recommend", help="为 canonical 用例推荐已批准知识")
    recommend.add_argument("case_file")

    bind = sub.add_parser("bind", help="把高置信度显式规则绑定到用例草稿")
    bind.add_argument("case_file")
    bind.add_argument("--output", required=True)
    bind.add_argument("--minimum-confidence", type=float, default=0.8)

    sub.add_parser("list-pending", help="列出待审批知识")
    args = parser.parse_args()
    knowledge = KnowledgeBase(Path(args.workspace)).load()

    if args.command == "search":
        values = knowledge.search(args.query)
        print(json.dumps(values, ensure_ascii=False, indent=2))
        return 0 if values else 1
    if args.command == "record-answer":
        scope = {key: value for key, value in {
            "project": args.project, "module": args.module, "feature": args.feature}.items() if value}
        record = knowledge.record_answer(question=args.question, answer=args.answer,
                                         scope=scope, knowledge_type=args.type)
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0
    if args.command == "approve":
        path = knowledge.approve(args.knowledge_id, approver=args.approver)
        print(path)
        return 0
    if args.command == "check-question":
        scope = {key: value for key, value in {
            "project": args.project, "module": args.module, "feature": args.feature}.items() if value}
        status = knowledge.question_status(args.question, scope=scope)
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0 if status["may_ask"] else 3
    if args.command == "mark-stale":
        print(knowledge.mark_stale(args.knowledge_id, reason=args.reason))
        return 0
    if args.command == "supersede":
        for path in knowledge.supersede(args.old_id, args.new_id, approver=args.approver):
            print(path)
        return 0
    if args.command == "conflicts":
        print(json.dumps(knowledge.conflicts(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "recommend":
        import yaml
        case = yaml.safe_load(Path(args.case_file).read_text(encoding="utf-8")) or {}
        print(json.dumps(knowledge.recommend_for_case(case), ensure_ascii=False, indent=2))
        return 0
    if args.command == "bind":
        import yaml
        case = yaml.safe_load(Path(args.case_file).read_text(encoding="utf-8")) or {}
        bound = knowledge.bind_recommendations(case, minimum_confidence=args.minimum_confidence)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(yaml.safe_dump(bound, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print(output)
        return 0
    values = knowledge.records(status="pending")
    print(json.dumps(values, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
