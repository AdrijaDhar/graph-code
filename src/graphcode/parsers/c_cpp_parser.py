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

import tree_sitter_c as tsc
import tree_sitter_cpp as tscpp


class CParser(LanguageParser):
    language_name = "c"

    def __init__(self, dialect: str = "c") -> None:
        self.dialect = dialect
        self.language_name = "cpp" if dialect == "cpp" else "c"
        self._parser = make_parser(tscpp if dialect == "cpp" else tsc)

    def parse_source(self, ctx: ParseContext) -> GraphBatch:
        batch = GraphBatch()
        tree = parse_tree(self._parser, ctx.source)
        module_node = add_module(batch, ctx)
        qprefix = module_node.props["qualified_name"]
        for node in walk(tree.root_node):
            if node.type == "preproc_include":
                path_n = named_child(node, "path")
                raw = node_text(ctx.source, path_n) if path_n else node_text(ctx.source, node)
                spec = raw.strip()
                if spec.startswith("<"):
                    continue
                spec = spec.strip('"<>')
                batch.add_edge(
                    GraphEdge(
                        type="IMPORTS",
                        from_id=module_node.id,
                        to_id=f"unresolved:{spec}",
                        props={"module": spec},
                    )
                )
            elif node.type in ("struct_specifier", "class_specifier"):
                name_n = named_child(node, "name")
                if not name_n:
                    continue
                name = node_text(ctx.source, name_n)
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
                for c in node.children:
                    if c.type == "base_class_clause":
                        base = node_text(ctx.source, c).replace(":", "").strip()
                        batch.add_edge(
                            GraphEdge(
                                type="INHERITS",
                                from_id=cls.id,
                                to_id=f"unresolved:{base}",
                                props={"base": base},
                            )
                        )
            elif node.type == "function_definition":
                declarator = named_child(node, "declarator")
                name = "anonymous"
                if declarator is not None:
                    for n in walk(declarator):
                        if n.type == "identifier":
                            name = node_text(ctx.source, n)
                            break
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


def CCppParser() -> CParser:
    return CParser("cpp")
