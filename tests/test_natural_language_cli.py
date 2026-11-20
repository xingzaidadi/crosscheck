import crosscheck_cli


def test_test_command_accepts_url_inside_natural_language(monkeypatch):
    captured = {}

    def fake_run(script, arguments):
        captured["script"] = script
        captured["arguments"] = arguments
        return 0

    monkeypatch.setattr(crosscheck_cli, "_run", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        ["crosscheck", "test", "帮我测试", "https://example.test/orders", "查询订单1001"],
    )
    assert crosscheck_cli.main() == 0
    assert captured["script"] == "scripts/agent_test.py"
    assert captured["arguments"][captured["arguments"].index("--url") + 1] == "https://example.test/orders"
    assert captured["arguments"][captured["arguments"].index("--instruction") + 1] == "帮我测试 查询订单1001"
    assert "--save-regression" not in captured["arguments"]


def test_test_command_only_saves_regression_when_requested(monkeypatch):
    captured = {}
    monkeypatch.setattr(crosscheck_cli, "_run", lambda script, arguments: captured.setdefault("args", arguments) and 0)
    monkeypatch.setattr(
        "sys.argv",
        ["crosscheck", "test", "https://example.test", "检查首页", "--save-regression"],
    )
    assert crosscheck_cli.main() == 0
    assert "--save-regression" in captured["args"]


def test_test_command_forwards_clarification_answers(monkeypatch):
    captured = {}
    monkeypatch.setattr(crosscheck_cli, "_run", lambda script, arguments: captured.setdefault("args", arguments) and 0)
    monkeypatch.setattr(
        "sys.argv",
        ["crosscheck", "test", "https://example.test", "帮我看看这个系统",
         "--answer", "测试订单中心", "--answer", "确认列表可见"],
    )
    assert crosscheck_cli.main() == 0
    assert captured["args"].count("--answer") == 2
