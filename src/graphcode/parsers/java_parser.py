from __future__ import annotations

from tree_sitter import Node

from graphcode.parsers.base import (
    LanguageParser,
    ParseContext,
    add_module,
    add_symbol,
    contains,
    make_parser,
    named_child,
    node_text,
    parse_tree,
    walk,
)
from graphcode.schema import GraphBatch, GraphEdge, GraphNode

import tree_sitter_java as tsjava


class JavaParser(LanguageParser):
    language_name = "java"

    def __init__(self) -> None:
        self._parser = make_parser(tsjava)

    def parse_source(self, ctx: ParseContext) -> GraphBatch:
        batch = GraphBatch()
        tree = parse_tree(self._parser, ctx.source)
        module_node = add_module(batch, ctx)
        qprefix = module_node.props["qualified_name"]
        for node in walk(tree.root_node):
            if node.type == "import_declaration":
                text = node_text(ctx.source, node)
                spec = text.replace("import", "").replace(";", "").strip()
                batch.add_edge(
                    GraphEdge(
                        type="IMPORTS",
                        from_id=module_node.id,
                        to_id=f"unresolved:{spec}",
                        props={"module": spec},
                    )
                )
            elif node.type in ("class_declaration", "interface_declaration"):
                name_n = named_child(node, "name")
                name = node_text(ctx.source, name_n) if name_n else "Anonymous"
                cls = add_symbol(
                    batch,
                    ctx,
                    label="Class",
                    name=name,
                    qualified_name=f"{qprefix}.{name}",
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                )
                contains(batch, module_node, cls)
                sc = named_child(node, "superclass") or named_child(node, "interfaces")
                if sc:
                    batch.add_edge(
                        GraphEdge(
                            type="INHERITS",
                            from_id=cls.id,
                            to_id=f"unresolved:{node_text(ctx.source, sc).strip()}",
                            props={"base": node_text(ctx.source, sc).strip()},
                        )
                    )
            elif node.type in ("method_declaration", "constructor_declaration"):
                name_n = named_child(node, "name")
                name = node_text(ctx.source, name_n) if name_n else "anonymous"
                fn = add_symbol(
                    batch,
                    ctx,
                    label="Function",
                    name=name,
                    qualified_name=f"{qprefix}.{name}",
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    extra={"is_method": True},
                )
                contains(batch, module_node, fn)
                body = named_child(node, "body")
                if body:
                    self._calls(batch, ctx, body, fn)
        return batch

    def _calls(self, batch: GraphBatch, ctx: ParseContext, body: Node, fn: GraphNode) -> None:
        for n in walk(body):
            if n.type == "method_invocation":
                name_n = named_child(n, "name")
                callee = node_text(ctx.source, name_n) if name_n else node_text(ctx.source, n)
                batch.add_edge(
                    GraphEdge(type="CALLS", from_id=fn.id, to_id=f"unresolved:{callee}", props={"callee": callee})
                )
