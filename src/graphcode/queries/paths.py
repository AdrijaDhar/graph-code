from __future__ import annotations

from collections import deque

from graphcode.loader.memory import MemoryStore
from graphcode.schema import GraphNode


def shortest_path(store: MemoryStore, src_key: str, dst_key: str, max_hops: int = 10) -> dict:
    a = store.find(src_key)
    b = store.find(dst_key)
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


def blast_radius(store: MemoryStore, key: str, direction: str = "upstream", max_hops: int = 5) -> dict:
    origin = store.find(key)
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
                seen.add(other)
                rec = _node(store.nodes[other])
                rec["via"] = e.type
                rec["hop"] = hops + 1
                nodes.append(rec)
                nxt.append(other)
        frontier = nxt
        hops += 1
    return {"origin": _node(origin), "direction": direction, "nodes": nodes}


def _node(n: GraphNode) -> dict:
    return {"id": n.id, "label": n.label, **n.props}
