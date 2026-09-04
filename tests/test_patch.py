from __future__ import annotations

from graphcode.patch import parse_file_blocks, unified_diff


def test_parse_file_blocks_single():
    text = "<<<FILE src/a.py>>>\nprint('hi')\n<<<END>>>\n"
    blocks = parse_file_blocks(text)
    assert blocks == [("src/a.py", "print('hi')\n")]


def test_parse_file_blocks_multiple():
    text = (
        "Some preamble the model shouldn't add, but parse anyway.\n"
        "<<<FILE a.py>>>\ncontent a\n<<<END>>>\n"
        "<<<FILE b/c.py>>>\ncontent b\n<<<END>>>\n"
    )
    blocks = parse_file_blocks(text)
    assert blocks == [("a.py", "content a\n"), ("b/c.py", "content b\n")]


def test_parse_file_blocks_none():
    assert parse_file_blocks("no blocks here") == []


def test_unified_diff_shows_change():
    diff = unified_diff("line1\nline2\n", "line1\nline2 changed\n", "f.py")
    assert "-line2" in diff
    assert "+line2 changed" in diff
    assert "a/f.py" in diff and "b/f.py" in diff


def test_unified_diff_empty_for_identical_content():
    assert unified_diff("same\n", "same\n", "f.py") == ""
