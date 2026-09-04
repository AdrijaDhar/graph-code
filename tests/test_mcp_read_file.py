from pathlib import Path

import graphcode.indexer as indexer
from graphcode.mcp import server

ROOT = Path(__file__).parent / "fixtures" / "mini_repo"


def test_read_file_returns_exact_content():
    server._svc().index_repo(ROOT, parallel=False)
    content = server.graph_read_file("src/utils.py")
    assert content == (ROOT / "src/utils.py").read_text()


def test_read_file_missing_path():
    server._svc().index_repo(ROOT, parallel=False)
    result = server.graph_read_file("no/such/file.py")
    assert result.startswith("error:")


def test_read_file_rejects_path_traversal():
    server._svc().index_repo(ROOT, parallel=False)
    result = server.graph_read_file("../../../../etc/passwd")
    assert result.startswith("error:")


def test_read_file_before_index_errors():
    indexer._SERVICE = None
    result = server.graph_read_file("anything.py")
    assert "no repo indexed" in result
