from __future__ import annotations

from graphcode.embed.encoder import embed_text, knn
from graphcode.indexer import IndexService
from graphcode.queries.paths import blast_radius, _node


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
