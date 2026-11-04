"""
入口。装配内核 + 适配器,加载用例,串行执行,出报告。

骨架阶段:只把线接通,具体实现看各 TODO。初期强制串行(哨兵/diff 前提是测试库安静)。
"""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from core.interfaces import DbAssertion, Expected, TestCase
from core.knowledge import KnowledgeBase
from core.marker import make_marker  # noqa: F401  (占位,避免未用告警)
from core.snapshot import SnapshotGuard
from core.verifier import Verifier
from core.cleaner import Cleaner
from core.reporter import Reporter
from core.executor import Executor
from core.workspace import set_workspace, kb_dir
from db.client import DbClient
from adapters.api_adapter import ApiAdapter
from adapters.playwright_adapter import PlaywrightAdapter  # noqa: F401


def load_case(path: str | Path) -> TestCase:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    exp = raw.get("expected", {})
    db_asserts = [
        DbAssertion(
            db=a["db"], table=a["table"], where=a["where"],
            row_count=(a.get("assert") or {}).get("row_count"),
            fields=(a.get("assert") or {}).get("fields", {}),
        )
        for a in exp.get("db", [])
    ]
    return TestCase(
        case_id=raw["case_id"],
        feature=raw["feature"],
        account_ref=(raw.get("preconditions") or {}).get("account", ""),
        data_prep=(raw.get("preconditions") or {}).get("data_prep"),
        steps=raw.get("steps", []),
        expected=Expected(
            page=exp.get("page", []),
            db=db_asserts,
            allowed_tables=(exp.get("diff_guard") or {}).get("allowed_tables", []),
        ),
        cleanup=raw.get("cleanup", []),
        raw=raw,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True, help="用例 yaml 路径")
    ap.add_argument("--kb", default=None, help="知识库目录(省略则用 <workspace>/knowledge_base)")
    ap.add_argument("--adapter", default="api", choices=["api", "playwright"])
    ap.add_argument("--workspace", default=None,
                    help="业务数据目录(省略则按 VTA_WORKSPACE / ./workspace / 仓库根 解析)")
    args = ap.parse_args()

    if args.workspace:
        set_workspace(args.workspace)

    # TODO: 从 <workspace>/config/db.yaml 读连接;credentials.yaml 读账号
    db = DbClient(dsn_readonly="TODO://readonly", dsn_write=None)
    kb = KnowledgeBase(args.kb or str(kb_dir())).load()

    adapter = (
        ApiAdapter(kb, credentials={}, base_url="TODO")
        if args.adapter == "api"
        else PlaywrightAdapter(kb, credentials={})
    )

    reporter = Reporter()
    executor = Executor(
        kb=kb, adapter=adapter,
        guard=SnapshotGuard(db), verifier=Verifier(db),
        cleaner=Cleaner(db), reporter=reporter,
    )

    case = load_case(args.case)
    executor.run_case(case)
    print(reporter.render())


if __name__ == "__main__":
    main()
