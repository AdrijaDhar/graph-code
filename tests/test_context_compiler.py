from pathlib import Path

from graphcode.context.compiler import compile_context
from graphcode.indexer import IndexService

ROOT = Path(__file__).parent / "fixtures" / "mini_repo"


def test_compile_context_mentions_structural_header(tmp_path):
    svc = IndexService(rocks_path=tmp_path / "rocks")
    svc.index_repo(ROOT, parallel=False)
    text = compile_context(
        svc.memory,
        root=ROOT,
        files=["src/api/controller.py"],
        symbols=["handle_request"],
        prompt="fix handle_request",
        max_tokens=2000,
    )
    assert "Structural Context" in text
