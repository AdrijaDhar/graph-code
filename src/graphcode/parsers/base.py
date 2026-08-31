from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from tree_sitter import Language, Node, Parser, Tree

from graphcode.schema import GraphBatch, GraphEdge, GraphNode, make_id, module_qid


@dataclass
class ParseContext:
    repo_hash: str
    path: str
    source: bytes
    language: str


class LanguageParser(Protocol):
    language_name: str

    def parse_source(self, ctx: ParseContext) -> GraphBatch: ...


def ts_language(module) -> Language:
    lang = module.language()
    if isinstance(lang, Language):
        return lang
    return Language(lang)


def make_parser(module) -> Parser:
    return Parser(ts_language(module))


def node_text(source: bytes, node: Node) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def walk(node: Node):
    yield node
    for child in node.children:
        yield from walk(child)


def named_child(node: Node, field: str) -> Node | None:
    return node.child_by_field_name(field)


def add_module(batch: GraphBatch, ctx: ParseContext) -> GraphNode:
    qn = module_qid(ctx.path)
    node = GraphNode(
        id=make_id(ctx.repo_hash, ctx.path, qn),
        label="Module",
        props={
            "path": ctx.path,
            "language": ctx.language,
            "qualified_name": qn,
            "name": qn.split(".")[-1],
        },
    )
    batch.add_node(node)
    return node


def add_symbol(
    batch: GraphBatch,
    ctx: ParseContext,
    *,
    label: str,
    name: str,
    qualified_name: str,
    start_line: int,
    end_line: int,
    extra: dict | None = None,
) -> GraphNode:
    props = {
        "name": name,
        "qualified_name": qualified_name,
        "path": ctx.path,
        "language": ctx.language,
        "start_line": start_line,
        "end_line": end_line,
    }
    if extra:
        props.update(extra)
    node = GraphNode(
        id=make_id(ctx.repo_hash, ctx.path, qualified_name),
        label=label,
        props=props,
    )
    batch.add_node(node)
    return node


def contains(batch: GraphBatch, parent: GraphNode, child: GraphNode) -> None:
    batch.add_edge(GraphEdge(type="CONTAINS", from_id=parent.id, to_id=child.id))


def parse_tree(parser: Parser, source: bytes) -> Tree:
    return parser.parse(source)
