"""Personalized PageRank over the code graph, seeded on the node(s) being edited.

Structural retrieval today (queries/paths.blast_radius) is unranked BFS — every node
within N hops is equally "relevant." PPR instead scores nodes by how much random-walk
probability concentrates near the seed, so a function three CALLS hops away but on the
only path from the seed outranks a function one hop away down a rarely-used branch.

Undirected by design (matching the doc's own PPR sketch): we want "structurally close
to the edit," not "reachable from the edit" — a caller is just as relevant as a callee.
"""

from __future__ import annotations

import networkx as nx

from graphcode.loader.memory import MemoryStore

# CONTAINS is structural nesting (module -> its functions), not a dependency signal,
# but it's the only edge that reaches many leaf nodes at all, so keep it, just weighted low.
EDGE_WEIGHT = {
    "CALLS": 1.0,
    "IMPORTS": 0.8,
    "INHERITS": 0.9,
    "CONTAINS": 0.3,
}


def build_graph(store: MemoryStore) -> nx.Graph:
    """Builds (and caches on the store) an undirected, edge-type-weighted graph."""
    if store._ppr_graph_cache is not None:
        return store._ppr_graph_cache
    g = nx.Graph()
    g.add_nodes_from(store.nodes.keys())
    for edges in store.out.values():
        for e in edges:
            if e.to_id not in store.nodes or e.from_id not in store.nodes:
                continue
            w = EDGE_WEIGHT.get(e.type, 0.5)
            if g.has_edge(e.from_id, e.to_id):
                g[e.from_id][e.to_id]["weight"] += w
            else:
                g.add_edge(e.from_id, e.to_id, weight=w)
    store._ppr_graph_cache = g
    return g


def personalized_pagerank(
    store: MemoryStore,
    seed_ids: list[str],
    alpha: float = 0.85,
    top: int = 50,
    radius: int = 4,
) -> list[tuple[str, float]]:
    """Returns up to `top` (node_id, score) pairs, ranked by PPR score, excluding seeds.
    Returns [] if none of the seeds are in the graph (isolated/unknown node).

    Runs on a bounded `radius`-hop neighborhood around the seeds, not the whole repo
    graph: relevance for an edit doesn't extend to unrelated modules five thousand
    nodes away, and localizing keeps latency roughly constant as the repo grows
    instead of scaling with total node count (full-graph pagerank on a ~3k-node repo
    measured ~250ms in benchmarks/perf_bench.py — well over the <200ms context-compile
    target; the local neighborhood is typically two orders of magnitude smaller)."""
    g = build_graph(store)
    seeds_in_graph = [s for s in seed_ids if s in g]
    if not seeds_in_graph:
        return []
    local = nx.Graph()
    for s in seeds_in_graph:
        local = nx.compose(local, nx.ego_graph(g, s, radius=radius))
    personalization = {s: 1.0 for s in seeds_in_graph}
    try:
        scores = nx.pagerank(local, alpha=alpha, personalization=personalization, weight="weight")
    except nx.PowerIterationFailedConvergence:
        return []
    seed_set = set(seed_ids)
    ranked = sorted(
        ((nid, score) for nid, score in scores.items() if nid not in seed_set),
        key=lambda pair: pair[1],
        reverse=True,
    )
    return ranked[:top]
