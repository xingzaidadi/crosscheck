"""缺陷5 回归:统一产品 CLI 必须暴露底层 agent_test.py 的关键开关(含 --scenarios)。

审计问题:场景执行闭环(--scenarios)只在 scripts/agent_test.py 存在,统一入口
crosscheck agent-test / crosscheck test 都没注册也不转发 —— 前几档修的"逐场景聚合、
结构化变换、业务断言"从产品入口根本点不到。

本测试锁住"开关超集"契约:底层 agent_test.py 面向用户的开关,统一 CLI 的 agent-test
子命令必须同名提供;且 --scenarios 在 agent-test 与 test 两个子命令都在。防再次漏接。

纯 argparse 内省 + 文本断言,不启动浏览器、不依赖 playwright。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _agent_test_options() -> set[str]:
    """从 scripts/agent_test.py 源码抓取其 argparse 注册的长选项(不执行 main)。"""
    src = (ROOT / "scripts" / "agent_test.py").read_text(encoding="utf-8")
    return set(re.findall(r'add_argument\(\s*"(--[a-z0-9-]+)"', src))


def _crosscheck_subparser_options(command: str) -> set[str]:
    src = (ROOT / "crosscheck_cli.py").read_text(encoding="utf-8")
    # 粗粒度:抓全文件里 <command 变量>.add_argument("--xxx") 的选项。
    # agent-test 子解析器变量名 agent_test;test 子解析器变量名 test。
    var = {"agent-test": "agent_test", "test": "test"}[command]
    pattern = rf'{var}\.add_argument\(\s*"(--[a-z0-9-]+)"'
    return set(re.findall(pattern, src))


def test_scenarios_switch_registered_in_agent_test_subcommand():
    opts = _crosscheck_subparser_options("agent-test")
    assert "--scenarios" in opts, f"crosscheck agent-test 必须注册 --scenarios,实得 {sorted(opts)}"


def test_scenarios_switch_registered_in_test_subcommand():
    opts = _crosscheck_subparser_options("test")
    assert "--scenarios" in opts, f"crosscheck test 必须注册 --scenarios,实得 {sorted(opts)}"


def test_agent_test_subcommand_is_switch_superset():
    """统一 CLI 的 agent-test 必须覆盖底层 agent_test.py 的全部用户开关。"""
    underlying = _agent_test_options()
    exposed = _crosscheck_subparser_options("agent-test")
    # 底层隐藏开关不强制暴露:--no-persist 是 SUPPRESS 内部项;--interactive-login 默认开、
    # 由转发层恒带,不需在子命令再注册。其余面向用户开关必须可达。
    internal = {"--no-persist", "--interactive-login"}
    missing = (underlying - exposed) - internal
    assert not missing, f"统一 CLI agent-test 漏接底层开关:{sorted(missing)}"


def test_scenarios_is_forwarded_not_just_registered():
    """注册还不够,必须真的转发给 scripts/agent_test.py。检查转发点含 scenarios。"""
    src = (ROOT / "crosscheck_cli.py").read_text(encoding="utf-8")
    # agent-test 分支:_forward 列表里含 "scenarios"
    assert re.search(r'_forward\(args,\s*\[[^\]]*"scenarios"', src, re.S), \
        "agent-test 分支应在 _forward 列表转发 scenarios"
    # test 分支:手工拼参处含 --scenarios
    assert '["--scenarios"]' in src, "test 分支应转发 --scenarios"
