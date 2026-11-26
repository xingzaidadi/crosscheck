"""缺陷6 回归:登录态自动发现有优先级,规划来源如实上报。

审计问题:
  · discovered-session.json 只写不读——人工登录一次后续仍反复要求登录。
    修复:_resolve_session 按 --session > profile .auth/<site>.json > .auth/discovered-session.json
    优先级回读真实存在的 session 文件。
  · 报告未说明 PASS 是确定性规则判的还是插件/LLM 判的。修复:_summarize_planning_source
    统计各步来源,provider_used 布尔 + mode + 说明,默认诚实标"未使用 LLM"。

纯函数测试,用临时目录造 .auth 文件,不启动浏览器。
"""
from pathlib import Path
from types import SimpleNamespace

from scripts.agent_test import _resolve_session, _summarize_planning_source


def _touch(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")


def test_explicit_session_wins(tmp_path):
    explicit = tmp_path / "my-session.json"
    _touch(explicit)
    # 即使也有 discovered,显式 --session 优先
    _touch(tmp_path / ".auth" / "discovered-session.json")
    res = _resolve_session(tmp_path, str(explicit), profile=None)
    assert res["source"] == "explicit"
    assert res["session"] == str(explicit)


def test_profile_auth_used_when_no_explicit(tmp_path):
    site_auth = tmp_path / ".auth" / "orders.json"
    _touch(site_auth)
    profile = SimpleNamespace(session_file=lambda: str(site_auth))
    res = _resolve_session(tmp_path, "", profile=profile)
    assert res["source"] == "profile_auth"
    assert res["session"] == str(site_auth)


def test_discovered_session_used_as_last_resort(tmp_path):
    discovered = tmp_path / ".auth" / "discovered-session.json"
    _touch(discovered)
    # profile 指向一个不存在的 .auth 文件 → 跳过,落到 discovered
    profile = SimpleNamespace(session_file=lambda: str(tmp_path / ".auth" / "missing.json"))
    res = _resolve_session(tmp_path, "", profile=profile)
    assert res["source"] == "discovered"
    assert res["session"] == str(discovered)


def test_no_session_anywhere_is_none(tmp_path):
    res = _resolve_session(tmp_path, "", profile=None)
    assert res["source"] == "none"
    assert res["session"] == ""


def test_explicit_nonexistent_falls_through(tmp_path):
    # --session 指了个不存在的文件 → 不认,继续按优先级找
    discovered = tmp_path / ".auth" / "discovered-session.json"
    _touch(discovered)
    res = _resolve_session(tmp_path, str(tmp_path / "nope.json"), profile=None)
    assert res["source"] == "discovered"


def test_planning_source_deterministic_by_default():
    execution = {"planner_decisions": [
        {"kind": "act", "source": "", "candidates": [{"score": 100}]},
        {"kind": "act", "source": "", "candidates": [{"score": 72}]},
    ]}
    summary = _summarize_planning_source(execution)
    assert summary["provider_used"] is False
    assert summary["mode"] == "deterministic"
    assert "未使用 LLM" in summary["note"]


def test_planning_source_flags_provider_when_used():
    execution = {"planner_decisions": [
        {"kind": "act", "source": "provider"},
        {"kind": "act", "source": ""},
    ]}
    summary = _summarize_planning_source(execution)
    assert summary["provider_used"] is True
    assert summary["mode"] == "provider_plugin"
    assert summary["step_source_counts"].get("provider") == 1


def test_planning_source_handles_empty_decisions():
    summary = _summarize_planning_source({})
    assert summary["provider_used"] is False
    assert summary["mode"] == "deterministic"
