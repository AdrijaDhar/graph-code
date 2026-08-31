from pathlib import Path

from graphcode.indexer import IndexService
from graphcode.queries.call_chain import call_chain
from graphcode.queries.paths import shortest_path

ROOT = Path(__file__).parent / "fixtures" / "mini_repo"


def test_call_chain_and_path(tmp_path):
    svc = IndexService(rocks_path=tmp_path / "rocks")
    svc.index_repo(ROOT, parallel=False)
    chain = call_chain(svc.memory, "handle_request")
    assert "paths" in chain
    sp = shortest_path(svc.memory, "ApiController", "parse_config")
    assert isinstance(sp.get("path"), list)
