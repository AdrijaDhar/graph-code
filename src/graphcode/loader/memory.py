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
        """Removes a module's nodes plus any edge touching them, in either direction.

        Was O(total graph size) regardless of how small the change: it scanned every
        node to find matches, scanned every other node's outgoing edge list to strip
        dangling pointers, then rebuilt `self.inn` from scratch. Profiling a 2000-file
        repo's single-file reindex (called up to 3x there — the file plus its ripple
        neighbors, see indexer.reindex_file) showed this as the single largest cost.
        Fixed to use `self.inn` as an index of "what points at this node" instead of
        rescanning the whole graph, so cost now scales with how many edges actually
        touch the dropped nodes, not with total repo size.
        """
        self._ppr_graph_cache = None
        drop = {
            i
            for i, n in self.nodes.items()
            if n.props.get("path") == path and n.props.get("org_id") == org_id
        }
        if not drop:
            return

        affected_sources: set[str] = set()
        for dst in drop:
            for e in self.inn.get(dst, []):
                affected_sources.add(e.from_id)
        for src in affected_sources - drop:
            if src in self.out:
                self.out[src] = [e for e in self.out[src] if e.to_id not in drop]

        affected_targets: set[str] = set()
        for src in drop:
            for e in self.out.get(src, []):
                affected_targets.add(e.to_id)
        for dst in affected_targets - drop:
            if dst in self.inn:
                self.inn[dst] = [e for e in self.inn[dst] if e.from_id not in drop]

        for i in drop:
            self.nodes.pop(i, None)
            self.out.pop(i, None)
            self.inn.pop(i, None)

    def counts(self) -> dict[str, int]:
        c: dict[str, int] = defaultdict(int)
        for n in self.nodes.values():
            c[n.label] += 1
        c["edges"] = sum(len(v) for v in self.out.values())
        return dict(c)

    def find(self, key: str, org_id: str | None = None) -> GraphNode | None:
        """`org_id`, when given, restricts matches to that org's nodes — needed because
        `_hydrate()` warm-loads every org's persisted snapshots into this same shared
        store, so an unscoped lookup can otherwise resolve a different tenant's symbol
        of the same name (a real cross-tenant leak in the multi-org SaaS app, since
        this is the resolution `blast_radius`/`shortest_path`/`call_chain` all use).

        Ranks every candidate by match specificity instead of returning the first
        loose match hit during dict iteration — a real, previously-reported bug:
        querying "feedback" could match a stray variable whose qualified_name merely
        *contained* "feedback" (e.g. in scripts/export_feedback_csv.py) before the
        loop ever reached the actually-intended function, purely because of insertion
        order. Exact id/path/qualified_name match wins outright; then a dotted-suffix
        match (searching "parse_config" should prefer ending in ".parse_config" over
        any substring hit); then a path suffix; substring match is the last resort,
        and among those, prefers non-Variable symbols and shorter (more specific)
        qualified names as tiebreakers."""
        direct = self.nodes.get(key)
        if direct is not None and (org_id is None or direct.props.get("org_id") == org_id):
            return direct

        best: tuple[int, int] | None = None
        best_node: GraphNode | None = None
        for n in self.nodes.values():
            if org_id is not None and n.props.get("org_id") != org_id:
                continue
            qn = n.props.get("qualified_name", "")
            path = n.props.get("path", "")
            if qn == key or path == key:
                score = 0
            elif qn.endswith("." + key):
                score = 1
            elif path.endswith(key):
                score = 2
            elif key in qn or key in path:
                score = 4 if n.label == "Variable" else 3
            else:
                continue
            rank = (score, len(qn))
            if best is None or rank < best:
                best, best_node = rank, n
        return best_node
