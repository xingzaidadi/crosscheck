"""Build a diff-triggered review-gate report from the immutable base-branch rules."""
import json
import subprocess

from core.review_gate import build_review_gate, write_review_gate

SAMPLE = """## RULE: alpha
- trigger: core/pipeline_runner.py
- check: check A
- incident: inc A

## RULE: beta
- trigger: core/circuit_breaker.py
- check: check B
- incident: inc B
"""


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _repo_with_review(tmp_path, name):
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    (repo / "REVIEW.md").write_text(SAMPLE, encoding="utf-8")
    _git(repo, "add", "REVIEW.md")
    _git(repo, "commit", "-m", "base")
    return repo


def test_build_review_gate_lists_matched_rules_with_why(tmp_path):
    repo = _repo_with_review(tmp_path, "r1")
    (repo / "core").mkdir()
    (repo / "core" / "circuit_breaker.py").write_text("x", encoding="utf-8")
    _git(repo, "add", "core/circuit_breaker.py")

    report = build_review_gate(repo, base_ref="main")
    assert report["rules_source"] == "base"
    names = [r["name"] for r in report["matched_rules"]]
    assert names == ["beta"]
    # Each matched rule carries check + incident so a human need not reverse-engineer it.
    assert report["matched_rules"][0]["check"] == "check B"
    assert report["matched_rules"][0]["incident"] == "inc B"
    assert any("check B" in action for action in report["next_actions"])
    assert report["content_hash"].startswith("sha256:")


def test_build_review_gate_absent_rules(tmp_path):
    repo = tmp_path / "r2"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    (repo / "x.txt").write_text("x", encoding="utf-8")
    _git(repo, "add", "x.txt")
    _git(repo, "commit", "-m", "init")
    report = build_review_gate(repo, base_ref="main")
    assert report["rules_source"] == "absent"
    assert report["matched_rules"] == []
    assert report["rules_active"] is False
    assert report["warnings"]  # absent must warn, so an empty checklist isn't misread as green


def test_write_review_gate(tmp_path):
    repo = _repo_with_review(tmp_path, "r3")
    report = build_review_gate(repo, base_ref="main")
    out = write_review_gate(report, tmp_path / "out" / "review_gate.json")
    assert out.exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["content_hash"] == report["content_hash"]
