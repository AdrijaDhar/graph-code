from __future__ import annotations

from graphcode.embed.encoder import embed_text, knn
from graphcode.indexer import IndexService
from graphcode.queries.paths import blast_radius, _node


def fuse_rrf(*ranked_lists: list[str], k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal rank fusion: score(c) = sum over lists containing c of 1/(k + rank).
    Scale-free across lists with different score distributions (PPR scores and cosine
    similarities aren't comparable directly, but ranks are), so no weight tuning needed
    to start. `k=60` is the standard RRF constant from the original TREC paper."""
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, node_id in enumerate(ranked):
            scores[node_id] = scores.get(node_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)


def semantic_search(svc: IndexService, query: str, k: int = 8, org_id: str = "local") -> dict:
    qv = embed_text(query)
    pairs = list(svc.rocks.iter_vectors(org_id))
    hits = knn(qv, pairs, k=k)
    results = []
    for fid, score in hits:
        node = svc.memory.nodes.get(fid)
        if not node:
            continue
        rec = _node(node)
        rec["score"] = score
        expand = blast_radius(svc.memory, fid, direction="both", max_hops=2)
        rec["neighbors"] = expand.get("nodes", [])[:12]
        results.append(rec)
    return {"query": query, "hits": results}
