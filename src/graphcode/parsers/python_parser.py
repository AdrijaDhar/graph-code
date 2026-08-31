from __future__ import annotations

import tree_sitter_python as tspython
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
from graphcode.schema import GraphBatch, GraphEdge


class PythonParser(LanguageParser):
    language_name = "python"

    def __init__(self) -> None:
        self._parser = make_parser(tspython)

    def parse_source(self, ctx: ParseContext) -> GraphBatch:
        batch = GraphBatch()
        tree = parse_tree(self._parser, ctx.source)
        module_node = add_module(batch, ctx)
        self._walk_block(batch, ctx, tree.root_node, module_node, module_node.props["qualified_name"], None)
        return batch

    def _walk_block(
        self,
        batch: GraphBatch,
        ctx: ParseContext,
        node: Node,
        container: object,
        qprefix: str,
        current_fn: object | None,
    ) -> None:
        from graphcode.schema import GraphNode

        container = container  # GraphNode
        for child in node.children:
            t = child.type
            if t == "class_definition":
                name_n = named_child(child, "name")
                name = node_text(ctx.source, name_n) if name_n else "Anonymous"
                qn = f"{qprefix}.{name}"
                cls = add_symbol(
                    batch,
                    ctx,
                    label="Class",
                    name=name,
                    qualified_name=qn,
                    start_line=child.start_point[0] + 1,
                    end_line=child.end_point[0] + 1,
                )
                contains(batch, container, cls)  # type: ignore[arg-type]
                super_n = named_child(child, "superclasses")
                if super_n:
                    for ident in walk(super_n):
                        if ident.type == "identifier":
                            base = node_text(ctx.source, ident)
                            batch.add_edge(
                                GraphEdge(
                                    type="INHERITS",
                                    from_id=cls.id,
                                    to_id=f"unresolved:{base}",
                                    props={"base": base},
                                )
                            )
                body = named_child(child, "body")
                if body:
                    self._walk_block(batch, ctx, body, cls, qn, current_fn)
            elif t == "function_definition":
                name_n = named_child(child, "name")
                name = node_text(ctx.source, name_n) if name_n else "anonymous"
                qn = f"{qprefix}.{name}"
                is_method = container.label == "Class"  # type: ignore[attr-defined]
                fn = add_symbol(
                    batch,
                    ctx,
                    label="Function",
                    name=name,
                    qualified_name=qn,
                    start_line=child.start_point[0] + 1,
                    end_line=child.end_point[0] + 1,
                    extra={"is_method": is_method},
                )
                contains(batch, container, fn)  # type: ignore[arg-type]
                body = named_child(child, "body")
                if body:
                    self._walk_block(batch, ctx, body, container, qprefix, fn)
            elif t in ("import_statement", "import_from_statement"):
                self._imports(batch, ctx, child, container)  # type: ignore[arg-type]
            elif t == "assignment" and current_fn is None and container.label in ("Module", "Class"):  # type: ignore[attr-defined]
                left = child.child_by_field_name("left")
                if left is not None and left.type == "identifier":
                    name = node_text(ctx.source, left)
                    qn = f"{qprefix}.{name}"
                    var = add_symbol(
                        batch,
                        ctx,
                        label="Variable",
                        name=name,
                        qualified_name=qn,
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        extra={"scope": container.label.lower()},  # type: ignore[attr-defined]
                    )
                    contains(batch, container, var)  # type: ignore[arg-type]
            elif t == "call" and current_fn is not None:
                callee = self._call_name(ctx, child)
                if callee:
                    batch.add_edge(
                        GraphEdge(
                            type="CALLS",
                            from_id=current_fn.id,  # type: ignore[attr-defined]
                            to_id=f"unresolved:{callee}",
                            props={"callee": callee},
                        )
                    )
            else:
                if child.child_count:
                    self._walk_block(batch, ctx, child, container, qprefix, current_fn)

    def _imports(self, batch: GraphBatch, ctx: ParseContext, node: Node, module: GraphNode) -> None:  # type: ignore[name-defined]
        from graphcode.schema import GraphNode as GN

        module = module
        text = node_text(ctx.source, node)
        mods: list[str] = []
        if node.type == "import_from_statement":
            mod_n = named_child(node, "module_name")
            if mod_n:
                mods.append(node_text(ctx.source, mod_n))
        else:
            for n in walk(node):
                if n.type in ("dotted_name", "identifier") and n.parent and n.parent.type == "import_statement":
                    mods.append(node_text(ctx.source, n))
                elif n.type == "dotted_name":
                    mods.append(node_text(ctx.source, n))
        if not mods:
            # fallback parse
            if text.startswith("from "):
                parts = text.split()
                if len(parts) >= 2:
                    mods.append(parts[1])
            elif text.startswith("import "):
                rest = text[len("import ") :]
                mods.extend(x.strip().split(" as ")[0] for x in rest.split(","))
        for m in mods:
            m = m.strip()
            if not m or m == "import":
                continue
            batch.add_edge(
                GraphEdge(
                    type="IMPORTS",
                    from_id=module.id,
                    to_id=f"unresolved:{m}",
                    props={"module": m, "raw": text.strip()},
                )
            )

    def _call_name(self, ctx: ParseContext, call: Node) -> str | None:
        func = named_child(call, "function")
        if func is None:
            return None
        text = node_text(ctx.source, func).strip()
        return text or None
