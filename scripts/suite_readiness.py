"""Diagnose canonical suite readiness without inventing missing business truth."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.knowledge import KnowledgeBase  # noqa: E402
from core.suite_dsl import load_suite, score_suite  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="分析 canonical 套件 READY 缺口和知识推荐")
    parser.add_argument("--suite", required=True)
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--output")
    args = parser.parse_args()
    suite, cases = load_suite(args.suite)
    score = score_suite(suite, cases)
    knowledge = KnowledgeBase(args.workspace).load()
    reasons = Counter()
    details = []
    for result, case in zip(score["results"], cases):
        for warning in result["warnings"]:
            reasons[warning] += 1
        for error in result["errors"]:
            reasons[error] += 1
        details.append({"case_id": case.get("case_id"), "title": case.get("title"),
                        "status": case.get("status"), "score": result["score"],
                        "errors": result["errors"], "warnings": result["warnings"],
                        "knowledge_recommendations": knowledge.recommend_for_case(case)})
    report = {"suite_id": score["suite_id"], "total": score["total"],
              "ready": score["execution_ready"], "average_score": score["average_score"],
              "top_gaps": reasons.most_common(), "cases": details}
    output = Path(args.output) if args.output else Path(args.suite) / "reports" / "readiness_diagnosis.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    return 0 if score["execution_ready"] == score["total"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
