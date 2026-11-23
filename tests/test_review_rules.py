"""Diff-triggered reliability checklist rules, read immutably from the base branch."""
import subprocess

from core.review_rules import (
    parse_review_md,
    read_base_review,
    changed_files,
    match_rules,
)

SAMPLE = """# header

## RULE: alpha
- trigger: core/pipeline_runner.py
- check: check A
- incident: inc A

## RULE: beta
- trigger: core/circuit_breaker.py, core/quality_gate.py
- check: check B
- incident: inc B
"""


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True,
                   capture_output=True, text=True)


def _init_repo(repo):
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")


def test_parse_review_md_extracts_rules():
    rules = parse_review_md(SAMPLE)
    assert [r["name"] for r in rules] == ["alpha", "beta"]
    assert rules[0]["triggers"] == ["core/pipeline_runner.py"]
    assert rules[1]["triggers"] == ["core/circuit_breaker.py", "core/quality_gate.py"]
    assert rules[0]["check"] == "check A"
    assert rules[1]["incident"] == "inc B"


def test_match_rules_returns_only_triggered():
    rules = parse_review_md(SAMPLE)
    matched = match_rules(rules, ["core/circuit_breaker.py", "core/unrelated.py"])
    assert [r["name"] for r in matched] == ["beta"]


def test_match_rules_empty_when_nothing_hits():
    rules = parse_review_md(SAMPLE)
    assert match_rules(rules, ["docs/README.md"]) == []


def test_match_rules_does_not_false_match_adjacent_filename():
    """trigger 'core/quality_gate.py' must not match 'core/quality_gate_modes.py'."""
    rules = parse_review_md("## RULE: qg\n- trigger: core/quality_gate.py\n- check: c\n- incident: i\n")
    assert match_rules(rules, ["core/quality_gate_modes.py"]) == []
    assert [r["name"] for r in match_rules(rules, ["core/quality_gate.py"])] == ["qg"]


def test_match_rules_matches_directory_prefix():
    """A directory trigger matches files under it."""
    rules = parse_review_md("## RULE: ui\n- trigger: core/ui/\n- check: c\n- incident: i\n")
    assert [r["name"] for r in match_rules(rules, ["core/ui/actions.py"])] == ["ui"]
    assert match_rules(rules, ["core/uixyz.py"]) == []


def test_read_base_review_uses_base_branch_not_working_tree(tmp_path):
    """Immutability: a working-tree edit to REVIEW.md must NOT change what is judged."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "REVIEW.md").write_text(SAMPLE, encoding="utf-8")
    _git(repo, "add", "REVIEW.md")
    _git(repo, "commit", "-m", "base review")

    # Now a change branch tampers with REVIEW.md in the working tree.
    (repo / "REVIEW.md").write_text("## RULE: injected\n- trigger: x\n- check: c\n- incident: i\n",
                                    encoding="utf-8")

    result = read_base_review(repo, base_ref="main")
    assert result["source"] == "base"
    # It must reflect the committed base version, not the tampered working tree.
    assert "alpha" in result["text"] and "beta" in result["text"]
    assert "injected" not in result["text"]


def test_read_base_review_absent_when_no_file(tmp_path):
    repo = tmp_path / "repo2"
    repo.mkdir()
    _init_repo(repo)
    (repo / "x.txt").write_text("x", encoding="utf-8")
    _git(repo, "add", "x.txt")
    _git(repo, "commit", "-m", "no review")
    result = read_base_review(repo, base_ref="main")
    assert result["source"] == "absent"
    assert result["text"] == ""


def test_read_base_review_bad_ref_is_distinct_from_absent(tmp_path):
    """A typo'd base_ref must NOT silently look like 'base has no REVIEW.md'."""
    repo = tmp_path / "repo_badref"
    repo.mkdir()
    _init_repo(repo)
    (repo / "REVIEW.md").write_text(SAMPLE, encoding="utf-8")
    _git(repo, "add", "REVIEW.md")
    _git(repo, "commit", "-m", "base")
    result = read_base_review(repo, base_ref="mian")  # typo
    assert result["source"] == "bad_ref"
    assert result["text"] == ""


def test_read_base_review_preserves_utf8(tmp_path):
    repo = tmp_path / "repo_utf8"
    repo.mkdir()
    _init_repo(repo)
    (repo / "REVIEW.md").write_text("## RULE: 中文\n- trigger: core/x.py\n- check: 检查中文\n- incident: 事故\n",
                                    encoding="utf-8")
    _git(repo, "add", "REVIEW.md")
    _git(repo, "commit", "-m", "base")
    result = read_base_review(repo, base_ref="main")
    assert "检查中文" in result["text"]


def test_read_base_review_degrades_when_not_git(tmp_path):
    result = read_base_review(tmp_path / "not-a-repo", base_ref="main")
    assert result["source"] == "no_git"
    assert result["text"] == ""


def test_changed_files_defaults_to_working_tree_not_whole_branch(tmp_path):
    """Default change set = uncommitted + untracked working-tree changes, NOT the
    entire branch divergence from base (which would drag in already-merged files)."""
    repo = tmp_path / "repo_wt"
    repo.mkdir()
    _init_repo(repo)
    (repo / "old.py").write_text("1", encoding="utf-8")
    _git(repo, "add", "old.py")
    _git(repo, "commit", "-m", "c1")
    # A committed-on-branch file that is "already history", plus fresh working-tree work.
    (repo / "committed.py").write_text("2", encoding="utf-8")
    _git(repo, "add", "committed.py")
    _git(repo, "commit", "-m", "c2")
    (repo / "working.py").write_text("3", encoding="utf-8")   # untracked, the real change
    (repo / "old.py").write_text("changed", encoding="utf-8")  # modified, the real change
    files = changed_files(repo, base_ref="main")
    assert "working.py" in files
    assert "old.py" in files
    # committed.py is branch history, not the current working-tree change.
    assert "committed.py" not in files
    # sorted for cross-environment hash stability
    assert files == sorted(files)


def test_changed_files_against_base_option(tmp_path):
    """Opt-in: against_base=True compares the branch vs base (merge-base...HEAD)."""
    repo = tmp_path / "repo_base"
    repo.mkdir()
    _init_repo(repo)
    (repo / "a.py").write_text("1", encoding="utf-8")
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-m", "init")
    _git(repo, "checkout", "-b", "feature")
    (repo / "b.py").write_text("new", encoding="utf-8")
    _git(repo, "add", "b.py")
    _git(repo, "commit", "-m", "feature work")
    files = changed_files(repo, base_ref="main", against_base=True)
    assert "b.py" in files
