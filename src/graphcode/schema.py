from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass
class GraphNode:
    id: str
    label: str
    props: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    type: str
    from_id: str
    to_id: str
    props: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphBatch:
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)

    def add_node(self, node: GraphNode) -> GraphNode:
        self.nodes.append(node)
        return node

    def add_edge(self, edge: GraphEdge) -> GraphEdge:
        self.edges.append(edge)
        return edge

    def merge(self, other: GraphBatch) -> None:
        self.nodes.extend(other.nodes)
        self.edges.extend(other.edges)

    def by_label(self, label: str) -> Iterable[GraphNode]:
        return (n for n in self.nodes if n.label == label)


def make_id(repo_hash: str, path: str, qualified_name: str) -> str:
    return f"{repo_hash}:{path}#{qualified_name}"


def module_qid(path: str) -> str:
    p = path.replace("\\", "/")
    for ext in (
        ".tsx",
        ".ts",
        ".jsx",
        ".mjs",
        ".cjs",
        ".js",
        ".py",
        ".go",
        ".java",
        ".rs",
        ".cpp",
        ".cc",
        ".cxx",
        ".hpp",
        ".hh",
        ".c",
        ".h",
    ):
        if p.endswith(ext):
            p = p[: -len(ext)]
            break
    return p.replace("/", ".")
