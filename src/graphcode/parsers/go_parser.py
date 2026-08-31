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

import tree_sitter_go as tsgo


class GoParser(LanguageParser):
    language_name = "go"

    def __init__(self) -> None:
        self._parser = make_parser(tsgo)

    def parse_source(self, ctx: ParseContext) -> GraphBatch:
        batch = GraphBatch()
        tree = parse_tree(self._parser, ctx.source)
        module_node = add_module(batch, ctx)
        qprefix = module_node.props["qualified_name"]
        current_fn: GraphNode | None = None
        for node in walk(tree.root_node):
            if node.type == "import_spec":
                path_n = named_child(node, "path") or next((c for c in node.children if c.type == "interpreted_string_literal"), None)
                if path_n:
                    spec = node_text(ctx.source, path_n).strip('"')
                    batch.add_edge(
                        GraphEdge(
                            type="IMPORTS",
                            from_id=module_node.id,
                            to_id=f"unresolved:{spec}",
                            props={"module": spec},
                        )
                    )
            elif node.type == "type_declaration":
                for c in walk(node):
                    if c.type == "type_identifier" and c.parent and c.parent.type == "type_spec":
                        name = node_text(ctx.source, c)
                        cls = add_symbol(
                            batch,
                            ctx,
                            label="Class",
                            name=name,
                            qualified_name=f"{qprefix}.{name}",
                            start_line=c.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                        )
                        contains(batch, module_node, cls)
            elif node.type == "method_declaration" or node.type == "function_declaration":
                name_n = named_child(node, "name")
                name = node_text(ctx.source, name_n) if name_n else "anonymous"
                recv = named_child(node, "receiver")
                if recv:
                    rtxt = node_text(ctx.source, recv)
                    qn = f"{qprefix}.{rtxt}.{name}"
                    is_method = True
                else:
                    qn = f"{qprefix}.{name}"
                    is_method = False
                fn = add_symbol(
                    batch,
                    ctx,
                    label="Function",
                    name=name,
                    qualified_name=qn,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    extra={"is_method": is_method},
                )
                contains(batch, module_node, fn)
                current_fn = fn
                body = named_child(node, "body")
                if body:
                    self._calls(batch, ctx, body, fn)
        return batch

    def _calls(self, batch: GraphBatch, ctx: ParseContext, body: Node, fn: GraphNode) -> None:
        for n in walk(body):
            if n.type == "call_expression":
                func = named_child(n, "function")
                if func is not None:
                    callee = node_text(ctx.source, func).strip()
                    batch.add_edge(
                        GraphEdge(type="CALLS", from_id=fn.id, to_id=f"unresolved:{callee}", props={"callee": callee})
                    )
