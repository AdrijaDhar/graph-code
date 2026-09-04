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

import tree_sitter_rust as tsrust


class RustParser(LanguageParser):
    language_name = "rust"

    def __init__(self) -> None:
        self._parser = make_parser(tsrust)

    def parse_source(self, ctx: ParseContext) -> GraphBatch:
        batch = GraphBatch()
        tree = parse_tree(self._parser, ctx.source)
        module_node = add_module(batch, ctx)
        qprefix = module_node.props["qualified_name"]
        for node in walk(tree.root_node):
            if node.type == "use_declaration":
                spec = node_text(ctx.source, node).replace("use", "").replace(";", "").strip()
                batch.add_edge(
                    GraphEdge(
                        type="IMPORTS",
                        from_id=module_node.id,
                        to_id=f"unresolved:{spec}",
                        props={"module": spec},
                    )
                )
            elif node.type == "mod_item" and named_child(node, "body") is None:
                name_n = named_child(node, "name")
                if name_n:
                    spec = node_text(ctx.source, name_n).strip()
                    batch.add_edge(
                        GraphEdge(
                            type="IMPORTS",
                            from_id=module_node.id,
                            to_id=f"unresolved:{spec}",
                            props={"module": spec},
                        )
                    )
            elif node.type == "struct_item":
                name_n = named_child(node, "name")
                name = node_text(ctx.source, name_n) if name_n else "Anon"
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
            elif node.type == "impl_item":
                trait = named_child(node, "trait")
                typ = named_child(node, "type")
                if trait is not None and typ is not None:
                    tname = node_text(ctx.source, typ).strip()
                    tr = node_text(ctx.source, trait).strip()
                    batch.add_edge(
                        GraphEdge(
                            type="INHERITS",
                            from_id=f"unresolved:{tname}",
                            to_id=f"unresolved:{tr}",
                            props={"base": tr, "impl_for": tname},
                        )
                    )
            elif node.type == "function_item":
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
                    extra={"is_method": False},
                )
                contains(batch, module_node, fn)
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
