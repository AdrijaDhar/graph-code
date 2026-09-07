import subprocess
from pathlib import Path

from graphcode.indexer import IndexService
from graphcode.pr_bot import build_comment, changed_line_ranges, changed_symbols


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    return repo


def test_changed_line_ranges_maps_hunks_to_new_file_lines(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "a.py").write_text("x = 1\ny = 2\nz = 3\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "branch", "base_ref")

    (repo / "a.py").write_text("x = 1\ny = 99\nz = 3\nw = 4\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "change")

    ranges = changed_line_ranges(repo, "base_ref", "HEAD")
    assert "a.py" in ranges
    # line 2 changed (y=99) and line 4 added (w=4); both should show up somewhere
    flat = [n for r in ranges["a.py"] for n in range(r[0], r[1] + 1)]
    assert 2 in flat
    assert 4 in flat


def test_pr_bot_reports_callers_of_changed_function(tmp_path):
    """End-to-end: a PR that only touches `helper`'s body should surface `run`, its
    only caller in a different file, via a real blast_radius traversal — not text
    search, since `run`'s own source never got touched by this diff at all."""
    repo = _make_repo(tmp_path)
    (repo / "utils.py").write_text("def helper():\n    return 1\n")
    (repo / "main.py").write_text("from utils import helper\n\n\ndef run():\n    return helper()\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "branch", "base_ref")

    (repo / "utils.py").write_text("def helper():\n    return 2  # changed\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "change helper")

    svc = IndexService(rocks_path=tmp_path / "rocks")
    svc.index_repo(repo, parallel=False)

    ranges = changed_line_ranges(repo, "base_ref", "HEAD")
    changed = changed_symbols(svc, ranges)
    names = {n.props.get("qualified_name", "") for n in changed}
    assert any("helper" in n for n in names)

    comment = build_comment(svc, changed)
    assert "helper" in comment
    assert "run" in comment


def test_pr_bot_reports_no_dependents_when_symbol_is_unused(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "solo.py").write_text("def unused():\n    return 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "branch", "base_ref")

    (repo / "solo.py").write_text("def unused():\n    return 2  # changed\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "change")

    svc = IndexService(rocks_path=tmp_path / "rocks")
    svc.index_repo(repo, parallel=False)

    ranges = changed_line_ranges(repo, "base_ref", "HEAD")
    changed = changed_symbols(svc, ranges)
    comment = build_comment(svc, changed)
    assert "No other indexed symbols depend on" in comment


def test_build_comment_empty_when_nothing_changed():
    assert build_comment(None, []) == ""
