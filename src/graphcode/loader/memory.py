from __future__ import annotations

from collections import defaultdict
from typing import Any

from graphcode.schema import GraphBatch, GraphEdge, GraphNode


class MemoryStore:
    """In-process graph used for tests and when Memgraph is not running."""

    def __init__(self) -> None:
        self.nodes: dict[str, GraphNode] = {}
        self.out: dict[str, list[GraphEdge]] = defaultdict(list)
        self.inn: dict[str, list[GraphEdge]] = defaultdict(list)
        self.repo_meta: dict[str, Any] = {}
        self._ppr_graph_cache = None  # invalidated on any mutation below; see queries/ppr.py

    def clear_org(self, org_id: str | None = None) -> None:
        self._ppr_graph_cache = None
        if org_id is None:
            self.nodes.clear()
            self.out.clear()
            self.inn.clear()
            return
        drop = [i for i, n in self.nodes.items() if n.props.get("org_id") == org_id]
        for i in drop:
            self.nodes.pop(i, None)
            self.out.pop(i, None)
            self.inn.pop(i, None)

    def load_batch(self, batch: GraphBatch, org_id: str = "local") -> None:
        self._ppr_graph_cache = None
        for n in batch.nodes:
            n.props.setdefault("org_id", org_id)
            self.nodes[n.id] = n
        for e in batch.edges:
            if e.to_id.startswith("unresolved:"):
                continue
            self.out[e.from_id].append(e)
            self.inn[e.to_id].append(e)

    def delete_module(self, path: str, org_id: str = "local") -> None:
        self._ppr_graph_cache = None
        drop = [
            i
            for i, n in self.nodes.items()
            if n.props.get("path") == path and n.props.get("org_id") == org_id
        ]
        for i in drop:
            self.nodes.pop(i, None)
            self.out.pop(i, None)
        for src, edges in list(self.out.items()):
            self.out[src] = [e for e in edges if e.to_id not in drop]
        self.inn = defaultdict(list)
        for src, edges in self.out.items():
            for e in edges:
                self.inn[e.to_id].append(e)

    def counts(self) -> dict[str, int]:
        c: dict[str, int] = defaultdict(int)
        for n in self.nodes.values():
            c[n.label] += 1
        c["edges"] = sum(len(v) for v in self.out.values())
        return dict(c)

    def find(self, key: str) -> GraphNode | None:
        if key in self.nodes:
            return self.nodes[key]
        for n in self.nodes.values():
            if n.props.get("path") == key or n.props.get("qualified_name") == key:
                return n
            if key in n.props.get("qualified_name", "") or n.props.get("path", "").endswith(key):
                return n
        return None
