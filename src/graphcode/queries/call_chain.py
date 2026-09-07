from __future__ import annotations

from graphcode.loader.memory import MemoryStore
from graphcode.queries.paths import _node


def call_chain(store: MemoryStore, key: str, max_depth: int = 5, org_id: str | None = None) -> dict:
    origin = store.find(key, org_id=org_id)
    if not origin:
        return {"paths": [], "error": "not found"}
    paths: list[list[dict]] = []
    seen_leaf: set[str] = set()

    def _in_org(nid: str) -> bool:
        return org_id is None or store.nodes[nid].props.get("org_id") == org_id

    def dfs(nid: str, acc: list[str], depth: int) -> None:
        if depth >= max_depth:
            paths.append([_node(store.nodes[x]) for x in acc if x in store.nodes])
            return
        callees = [
            e.to_id
            for e in store.out.get(nid, [])
            if e.type == "CALLS" and e.to_id in store.nodes and _in_org(e.to_id)
        ]
        if not callees:
            paths.append([_node(store.nodes[x]) for x in acc if x in store.nodes])
            return
        for c in callees:
            if c in acc:
                continue
            seen_leaf.add(c)
            dfs(c, acc + [c], depth + 1)

    start = origin.id
    if origin.label != "Function":
        kids = [e.to_id for e in store.out.get(origin.id, []) if e.type == "CONTAINS"]
        fns = [k for k in kids if store.nodes.get(k) and store.nodes[k].label == "Function" and _in_org(k)]
        for f in fns:
            dfs(f, [f], 0)
    else:
        dfs(start, [start], 0)
    paths.sort(key=lambda p: len(p), reverse=True)
    return {"origin": _node(origin), "paths": paths[:50]}
