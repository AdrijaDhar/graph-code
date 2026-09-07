from __future__ import annotations

from collections import deque

from graphcode.loader.memory import MemoryStore
from graphcode.schema import GraphNode


def shortest_path(
    store: MemoryStore, src_key: str, dst_key: str, max_hops: int = 10, org_id: str | None = None
) -> dict:
    a = store.find(src_key, org_id=org_id)
    b = store.find(dst_key, org_id=org_id)
    if not a or not b:
        return {"path": [], "error": "symbol not found"}
    if a.id == b.id:
        return {"path": [_node(a)], "hops": 0}
    prev: dict[str, tuple[str, str]] = {}
    q = deque([a.id])
    seen = {a.id}
    found = False
    while q:
        cur = q.popleft()
        hops = 0
        t = cur
        while t in prev:
            t = prev[t][0]
            hops += 1
        if hops >= max_hops:
            continue
        for e in list(store.out.get(cur, [])) + list(store.inn.get(cur, [])):
            nxt = e.to_id if e.from_id == cur else e.from_id
            if nxt in seen or nxt not in store.nodes:
                continue
            if org_id is not None and store.nodes[nxt].props.get("org_id") != org_id:
                continue
            seen.add(nxt)
            prev[nxt] = (cur, e.type)
            if nxt == b.id:
                found = True
                q.clear()
                break
            q.append(nxt)
    if not found:
        return {"path": [], "from": _node(a), "to": _node(b)}
    chain = [b.id]
    while chain[-1] != a.id:
        chain.append(prev[chain[-1]][0])
    chain.reverse()
    steps = []
    for i, nid in enumerate(chain):
        rec = _node(store.nodes[nid])
        if i:
            rec["via"] = prev[nid][1]
        steps.append(rec)
    return {"path": steps, "hops": len(steps) - 1}


def blast_radius(
    store: MemoryStore, key: str, direction: str = "upstream", max_hops: int = 5, org_id: str | None = None
) -> dict:
    # touched to trigger the PR bot demo
    origin = store.find(key, org_id=org_id)
    if not origin:
        return {"nodes": [], "error": "not found"}
    seen = {origin.id}
    frontier = [origin.id]
    nodes = [_node(origin)]
    hops = 0
    while frontier and hops < max_hops:
        nxt: list[str] = []
        for nid in frontier:
            edges = store.inn.get(nid, []) if direction == "upstream" else store.out.get(nid, [])
            if direction == "both":
                edges = list(store.inn.get(nid, [])) + list(store.out.get(nid, []))
            for e in edges:
                other = e.from_id if e.to_id == nid else e.to_id
                if other in seen or other not in store.nodes:
                    continue
                if org_id is not None and store.nodes[other].props.get("org_id") != org_id:
                    continue
                seen.add(other)
                rec = _node(store.nodes[other])
                rec["via"] = e.type
                rec["hop"] = hops + 1
                rec["from"] = nid
                nodes.append(rec)
                nxt.append(other)
        frontier = nxt
        hops += 1
    return {"origin": _node(origin), "direction": direction, "nodes": nodes}


def _node(n: GraphNode) -> dict:
    return {"id": n.id, "label": n.label, **n.props}


def graph_overview(store: MemoryStore, org_id: str | None = None, max_nodes: int = 500) -> dict:
    """A file-level dependency map of the whole indexed repo — every Module node plus
    the IMPORTS edges between them, sized by how many functions/classes each file
    contains. This is deliberately module-granularity, not every individual function:
    a real repo's function-level graph can run into thousands of nodes (confirmed
    live: one test repo had 5,484 functions), which is both too dense to render
    meaningfully and far more than a "here's the shape of this codebase" overview
    needs — a developer opening this wants to see how files relate, not a hairball."""

    def in_org(n: GraphNode) -> bool:
        return org_id is None or n.props.get("org_id") == org_id

    modules = {n.id: n for n in store.nodes.values() if n.label == "Module" and in_org(n)}

    size_by_module: dict[str, int] = {mid: 0 for mid in modules}
    for e in store.out.values():
        for edge in e:
            if edge.type == "CONTAINS" and edge.from_id in size_by_module and edge.to_id in store.nodes:
                child = store.nodes[edge.to_id]
                if child.label in ("Function", "Class"):
                    size_by_module[edge.from_id] += 1

    edges: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()
    for mid in modules:
        for e in store.out.get(mid, []):
            if e.type == "IMPORTS" and e.to_id in modules and e.to_id != mid:
                pair = (mid, e.to_id)
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    edges.append({"source": mid, "target": e.to_id})

    ranked = sorted(modules.values(), key=lambda n: size_by_module.get(n.id, 0), reverse=True)[:max_nodes]
    kept_ids = {n.id for n in ranked}
    nodes = [
        {
            **_node(n),
            "size": size_by_module.get(n.id, 0),
        }
        for n in ranked
    ]
    kept_edges = [e for e in edges if e["source"] in kept_ids and e["target"] in kept_ids]
    return {"nodes": nodes, "edges": kept_edges, "truncated": len(modules) > max_nodes}


def suggest_starting_points(store: MemoryStore, org_id: str | None = None, top: int = 8) -> dict:
    """Ranks functions/classes by real dependency in-degree — how many *distinct*
    other functions/classes call or inherit from it — as a fast, deterministic, free
    proxy for "how central is this to the codebase." Answers the actual first
    question after indexing an unfamiliar repo: not "what do I query" (a new user has
    no idea yet), but "what's actually worth understanding first." Deliberately not
    LLM-backed: this is graph centrality computed in one pass over data already in
    memory — same cost and same answer every time, no API key, no rate limit, no
    latency, for a feature whose whole job is to be the very first thing a user sees."""

    def in_org(n: GraphNode) -> bool:
        return org_id is None or n.props.get("org_id") == org_id

    callers: dict[str, set[str]] = {}
    for edges in store.out.values():
        for e in edges:
            if e.type not in ("CALLS", "INHERITS"):
                continue
            if e.to_id not in store.nodes or e.from_id not in store.nodes:
                continue
            target = store.nodes[e.to_id]
            if target.label not in ("Function", "Class") or not in_org(target):
                continue
            callers.setdefault(e.to_id, set()).add(e.from_id)

    ranked = sorted(callers.items(), key=lambda pair: len(pair[1]), reverse=True)[:top]
    return {
        "suggestions": [{**_node(store.nodes[nid]), "dependent_count": len(callset)} for nid, callset in ranked]
    }
