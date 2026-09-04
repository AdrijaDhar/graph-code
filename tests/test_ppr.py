from __future__ import annotations

from graphcode.loader.memory import MemoryStore
from graphcode.queries.ppr import build_graph, personalized_pagerank
from graphcode.schema import GraphEdge, GraphNode


def _chain_store() -> MemoryStore:
    """seed -CALLS-> near -CALLS-> far, plus an unrelated isolated pair."""
    store = MemoryStore()
    nodes = [
        GraphNode(id="seed", label="Function", props={"name": "seed"}),
        GraphNode(id="near", label="Function", props={"name": "near"}),
        GraphNode(id="far", label="Function", props={"name": "far"}),
        GraphNode(id="unrelated_a", label="Function", props={"name": "a"}),
        GraphNode(id="unrelated_b", label="Function", props={"name": "b"}),
    ]
    edges = [
        GraphEdge(type="CALLS", from_id="seed", to_id="near"),
        GraphEdge(type="CALLS", from_id="near", to_id="far"),
        GraphEdge(type="CALLS", from_id="unrelated_a", to_id="unrelated_b"),
    ]
    from graphcode.schema import GraphBatch

    store.load_batch(GraphBatch(nodes=nodes, edges=edges))
    return store


def test_build_graph_is_undirected_and_weighted():
    store = _chain_store()
    g = build_graph(store)
    assert g.has_edge("seed", "near")
    assert g.has_edge("near", "seed")  # undirected
    assert g["seed"]["near"]["weight"] == 1.0  # CALLS weight


def test_build_graph_is_cached():
    store = _chain_store()
    g1 = build_graph(store)
    g2 = build_graph(store)
    assert g1 is g2


def test_cache_invalidated_on_load_batch():
    store = _chain_store()
    g1 = build_graph(store)
    from graphcode.schema import GraphBatch

    store.load_batch(GraphBatch(nodes=[GraphNode(id="extra", label="Function", props={})], edges=[]))
    g2 = build_graph(store)
    assert g1 is not g2
    assert "extra" in g2


def test_ppr_ranks_closer_nodes_higher():
    store = _chain_store()
    ranked = personalized_pagerank(store, ["seed"], top=10)
    ids = [nid for nid, _ in ranked]
    assert "near" in ids and "far" in ids
    assert ids.index("near") < ids.index("far")
    assert "unrelated_a" not in ids or ids.index("near") < ids.index("unrelated_a")


def test_ppr_excludes_seed_from_results():
    store = _chain_store()
    ranked = personalized_pagerank(store, ["seed"], top=10)
    assert "seed" not in [nid for nid, _ in ranked]


def test_ppr_unknown_seed_returns_empty():
    store = _chain_store()
    assert personalized_pagerank(store, ["does-not-exist"], top=10) == []


def test_ppr_respects_top_limit():
    store = _chain_store()
    ranked = personalized_pagerank(store, ["seed"], top=1)
    assert len(ranked) == 1
