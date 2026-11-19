import json
from pathlib import Path

from scripts.render_ui_report import render_summary


def test_ui_report_renders_source_actions_assertions_and_run_relative_evidence(tmp_path: Path):
    run_dir = tmp_path / "run"
    case_dir = run_dir / "TC115"
    case_dir.mkdir(parents=True)
    (case_dir / "before.png").write_bytes(b"png")
    (case_dir / "after.png").write_bytes(b"png")
    (case_dir / "recording.webm").write_bytes(b"webm")
    (case_dir / "page.html").write_text("<main>list</main>", encoding="utf-8")
    summary = {
        "run_id": "report-test",
        "cases": [{
            "case_id": "TC115", "title": "默认待处理", "verdict": "INCONCLUSIVE",
            "source_steps": "打开需求列表\n点击待处理",
            "source_expected": "默认展示待处理单据",
            "source_preconditions": "使用只读账号",
            "source_module": "需求管理",
            "execution": {"technical_verdict": "PASS", "actions_replayed": [
                {"action": "click", "target": "待处理", "ok": True},
            ]},
            "acceptance": {"verdict": "INCONCLUSIVE", "coverage": 0.5,
                           "results": [{"value": "待处理", "actual": True, "passed": True}],
                           "unresolved": ["展示状态符合预期"]},
            "evidence": {"screenshots": [str(case_dir / "before.png"), "TC115/after.png"],
                         "video": "TC115/recording.webm", "html": "TC115/page.html",
                         "network_diagnostics": {"count": 1, "requests": []}},
        }, {
            "case_id": "TC116", "title": "筛选", "verdict": "BLOCKED",
            "reason": "未执行：缺少角色输入", "execution": {}, "acceptance": {}, "evidence": {},
        }],
    }
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")

    report_path = render_summary(run_dir)

    report = report_path.read_text(encoding="utf-8")
    assert "原始步骤" in report and "打开需求列表" in report
    assert "原始预期" in report and "默认展示待处理单据" in report
    assert "步骤 1" in report and "断言覆盖率" in report
    assert "<img" in report and "<video controls" in report
    assert "TC115/before.png" in report and "C:\\" not in report
    assert "UI 诊断" in report and "API（未执行）" in report and "DB（未执行）" in report
    assert "未执行，无截图、录屏或页面 HTML" in report
    assert summary_path.read_text(encoding="utf-8") == json.dumps(summary, ensure_ascii=False)


def test_ui_report_rejects_evidence_outside_run_directory(tmp_path: Path):
    run_dir = tmp_path / "run"
    outside = tmp_path / "secret.png"
    outside.write_bytes(b"png")
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(json.dumps({
        "run_id": "path-test",
        "cases": [{"case_id": "TC1", "title": "blocked", "verdict": "BLOCKED",
                   "execution": {}, "acceptance": {},
                   "evidence": {"screenshots": [str(outside)]}}],
    }), encoding="utf-8")

    report = render_summary(run_dir).read_text(encoding="utf-8")

    assert str(outside) not in report
    assert "截图 1 不存在或不在运行目录内" in report


def test_inconclusive_is_not_rendered_as_inconsistent(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(json.dumps({
        "run_id": "inconclusive-test",
        "cases": [{
            "case_id": "TC1", "title": "partial evidence", "verdict": "INCONCLUSIVE",
            "execution": {"technical_verdict": "PASS", "actions_replayed": []},
            "acceptance": {"verdict": "INCONCLUSIVE", "coverage": 0.5,
                           "results": [{"value": "状态", "actual": True, "passed": True}],
                           "unresolved": ["业务规则"]},
            "evidence": {},
        }],
    }, ensure_ascii=False), encoding="utf-8")

    report = render_summary(run_dir).read_text(encoding="utf-8")

    assert "无法判定（证据不完整）" in report
    assert "UI 业务验收" in report
    assert "不一致 ✗" not in report
