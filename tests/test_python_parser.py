from pathlib import Path

from graphcode.indexer import IndexService
from graphcode.parsers.base import ParseContext
from graphcode.parsers.python_parser import PythonParser
from graphcode.queries.paths import blast_radius, shortest_path

ROOT = Path(__file__).parent / "fixtures" / "mini_repo"


def test_python_parser_extracts_functions_and_imports():
    src = (ROOT / "src/utils.py").read_bytes()
    batch = PythonParser().parse_source(
        ParseContext(repo_hash="abc", path="src/utils.py", source=src, language="python")
    )
    names = {n.props["name"] for n in batch.nodes if n.label == "Function"}
    assert "parse_config" in names
    assert any(n.label == "Module" for n in batch.nodes)


def test_index_python_and_shortest_path(tmp_path):
    svc = IndexService(rocks_path=tmp_path / "rocks")
    result = svc.index_repo(ROOT, parallel=False)
    assert result["counts"].get("Module", 0) >= 2
    sp = shortest_path(svc.memory, "src/api/controller.py", "src/utils.py")
    assert sp.get("path"), sp
    br = blast_radius(svc.memory, "parse_config", direction="upstream")
    assert br.get("nodes")
