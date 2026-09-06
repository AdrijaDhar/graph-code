from __future__ import annotations

import asyncio
import io
import sys
from pathlib import Path

from graphcode.mcp.client import GraphCodeAgent


def _agent(tmp_path: Path) -> GraphCodeAgent:
    return GraphCodeAgent(session=None, repo_path=tmp_path)


def test_apply_response_writes_on_yes(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("old\n")
    agent = _agent(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _: "y")
    agent.apply_response("<<<FILE a.py>>>\nnew\n<<<END>>>\n")
    assert (tmp_path / "a.py").read_text() == "new\n"


def test_apply_response_skips_on_no(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("old\n")
    agent = _agent(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _: "n")
    agent.apply_response("<<<FILE a.py>>>\nnew\n<<<END>>>\n")
    assert (tmp_path / "a.py").read_text() == "old\n"


def test_apply_response_skips_gracefully_on_eof(tmp_path):
    """Regression test: input() raising EOFError (piped/closed stdin) used to crash
    the whole CLI with a raw traceback instead of just skipping the file."""
    (tmp_path / "a.py").write_text("old\n")
    agent = _agent(tmp_path)
    old_stdin = sys.stdin
    sys.stdin = io.StringIO("")
    try:
        agent.apply_response("<<<FILE a.py>>>\nnew\n<<<END>>>\n")
    finally:
        sys.stdin = old_stdin
    assert (tmp_path / "a.py").read_text() == "old\n"


def test_apply_response_creates_new_file(tmp_path, monkeypatch):
    agent = _agent(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _: "y")
    agent.apply_response("<<<FILE new/nested/b.py>>>\ncontent\n<<<END>>>\n")
    assert (tmp_path / "new/nested/b.py").read_text() == "content\n"


def test_apply_response_prints_raw_text_when_no_file_blocks(tmp_path, capsys):
    agent = _agent(tmp_path)
    agent.apply_response("just a plain answer, no patch")
    assert "just a plain answer" in capsys.readouterr().out


def test_call_tool_truncates_long_results(tmp_path):
    class FakeBlock:
        type = "text"
        text = "x" * 10000

    class FakeResult:
        content = [FakeBlock()]
        isError = False

    class FakeSession:
        async def call_tool(self, name, arguments):
            return FakeResult()

    agent = GraphCodeAgent(session=FakeSession(), repo_path=tmp_path)
    result = asyncio.run(agent._call_tool("graph_read_file", {"path": "big.py"}))
    assert len(result) < 10000
    assert "truncated" in result


def test_call_tool_surfaces_server_errors(tmp_path):
    class FakeBlock:
        type = "text"
        text = "boom"

    class FakeResult:
        content = [FakeBlock()]
        isError = True

    class FakeSession:
        async def call_tool(self, name, arguments):
            return FakeResult()

    agent = GraphCodeAgent(session=FakeSession(), repo_path=tmp_path)
    result = asyncio.run(agent._call_tool("graph_status", {}))
    assert "error calling graph_status" in result
