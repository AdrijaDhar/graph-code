from pathlib import Path

from graphcode.indexer import IndexService
from graphcode.loader.rocksdb_store import RocksStore
from graphcode.queries.hybrid import semantic_search
from graphcode.schema import GraphBatch, GraphNode

ROOT = Path(__file__).parent / "fixtures" / "mini_repo"


def test_polyglot_index_and_semantic(tmp_path):
    svc = IndexService(rocks_path=tmp_path / "rocks")
    result = svc.index_repo(ROOT, parallel=True)
    langs = {n.props.get("language") for n in svc.memory.nodes.values() if n.label == "Module"}
    assert "python" in langs
    assert langs & {"go", "java", "c", "rust", "cpp", "typescript", "javascript"}
    hits = semantic_search(svc, "parse config key value", k=5)
    assert "hits" in hits
    assert result["files"] >= 5


def test_rocks_hydrate_roundtrip(tmp_path):
    store = RocksStore(tmp_path / "rocks")
    batch = GraphBatch()
    batch.add_node(GraphNode(id="1", label="Module", props={"path": "a.py"}))
    store.save_snapshot("o", "r", batch)
    loaded = store.load_snapshot("o", "r")
    assert loaded and loaded.nodes[0].id == "1"
