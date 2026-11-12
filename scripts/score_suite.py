"""Score a canonical suite and write machine-readable plus Markdown results."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.suite_dsl import load_suite, score_suite, write_score


def main() -> int:
    parser = argparse.ArgumentParser(description="校验并评分结构化测试套件")
    parser.add_argument("suite_dir")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    suite, cases = load_suite(args.suite_dir)
    score = score_suite(suite, cases)
    output = Path(args.out) if args.out else Path(args.suite_dir) / "suite_score.json"
    write_score(score, output)
    md = output.with_suffix(".md")
    lines = [f"# Suite Structure Score: {score['suite_id']}", "", f"- 总用例: {score['total']}",
             f"- Schema 合规: {score['schema_valid']}", f"- 可进入编译: {score['execution_ready']}",
             f"- 平均结构分(不代表业务正确性): {score['average_score']}", "",
             "|用例|分数|状态|错误|警告|", "|---|---:|---|---|---|"]
    for item in score["results"]:
        lines.append(f"|{item['case_id']}|{item['score']}|"
                     f"{'COMPILE_CANDIDATE' if item['execution_ready'] else 'DRAFT'}|"
                     f"{'; '.join(item['errors']) or '—'}|{'; '.join(item['warnings']) or '—'}|")
    md.write_text("\n".join(lines), encoding="utf-8")
    print(f"suite={score['suite_id']} total={score['total']} compile_candidates={score['execution_ready']} average={score['average_score']}")
    print(f"json={output}\nmarkdown={md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
