"""三段式报告汇总 + 渲染 + db 工厂装配(离线)。

跑:python tests/test_stage_report.py  或  pytest tests/test_stage_report.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.stage_report import render_html, summarize, write_report  # noqa: E402
from core.three_stage_wiring import make_readonly_db_factory  # noqa: E402
from core.workspace import set_workspace  # noqa: E402


def _seed_case(root: Path, case_id: str, checkpoint: dict) -> None:
    case_dir = root / case_id
    (case_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (case_dir / "stage_checkpoint.json").write_text(
        json.dumps(checkpoint, ensure_ascii=False), encoding="utf-8")


def test_summarize_counts_pass_reject_notrun():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _seed_case(root, "TC01", {
            "spec": {"verdict": "pass", "attempts": 1, "artifact_hash": "a" * 64},
            "actions": {"verdict": "pass", "attempts": 1, "artifact_hash": "b" * 64},
            "evidence": {"verdict": "pass", "attempts": 1, "artifact_hash": "c" * 64},
        })
        _seed_case(root, "TC02", {
            "spec": {"verdict": "reject", "attempts": 2, "reasons": ["缺断言"],
                     "artifact_hash": "d" * 64},
        })
        summary = summarize(root)
        assert summary["totals"]["cases"] == 2
        assert summary["totals"]["completed"] == 1
        assert summary["totals"]["stopped"] == 1
        assert summary["totals"]["by_stage"]["spec"] == {"pass": 1, "reject": 1, "not_run": 0}
        assert summary["totals"]["by_stage"]["evidence"] == {"pass": 1, "reject": 0, "not_run": 1}
        tc02 = next(c for c in summary["cases"] if c["case_id"] == "TC02")
        assert tc02["stopped_at"] == "spec"


def test_render_and_write_report():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _seed_case(root, "TC01", {
            "spec": {"verdict": "reject", "attempts": 2, "reasons": ["draft 未人审"],
                     "artifact_hash": "e" * 64},
        })
        summary = summarize(root)
        html = render_html(summary)
        assert "三段式流水线报告" in html and "draft 未人审" in html and "停在 spec" in html
        out = write_report(root)
        assert out.exists() and (root / "report.json").exists()
        assert "三段式流水线报告" in out.read_text(encoding="utf-8")


def test_db_factory_none_without_config():
    # 空 fixture workspace(无 db.yaml 或占位)-> 工厂为 None,evidence 不崩,降级 UI 源
    set_workspace(Path(__file__).resolve().parent / "fixtures" / "workspace")
    factory = make_readonly_db_factory("nonexistent_db")
    assert factory is None


def test_report_renders_clickable_thumbnails():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "TC01" / "artifacts").mkdir(parents=True)
        shot = root / "TC01" / "artifacts" / "shot.png"
        shot.write_bytes(b"PNG")
        (root / "TC01" / "stage_checkpoint.json").write_text(
            json.dumps({"spec": {"verdict": "pass"}}), encoding="utf-8")
        (root / "TC01" / "artifacts" / "actions.json").write_text(
            json.dumps({"actions": {"evidence": [str(shot)], "steps": [{"index": 0}]}}),
            encoding="utf-8")
        summary = summarize(root)
        assert summary["cases"][0]["evidence_images"] == [str(shot)]
        html = render_html(summary)
        assert "<img" in html and "file:" in html and "UI 证据" in html


def main() -> None:
    test_summarize_counts_pass_reject_notrun()
    test_render_and_write_report()
    test_db_factory_none_without_config()
    test_report_renders_clickable_thumbnails()
    print("test_stage_report ✅ 全部通过")


if __name__ == "__main__":
    main()
