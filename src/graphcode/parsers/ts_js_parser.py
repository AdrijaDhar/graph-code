from __future__ import annotations

import json
from pathlib import Path

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

try:
    import tree_sitter_javascript as tsjs
except ImportError:  # pragma: no cover
    tsjs = None

try:
    import tree_sitter_typescript as tsts
except ImportError:  # pragma: no cover
    tsts = None


def load_tsconfig_paths(repo_root: Path) -> tuple[str, dict[str, list[str]]]:
    cfg = repo_root / "tsconfig.json"
    if not cfg.is_file():
        return ".", {}
    try:
        raw = cfg.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return ".", {}
    compiler = data.get("compilerOptions") or {}
    base = compiler.get("baseUrl") or "."
    paths = compiler.get("paths") or {}
    return base, paths


def resolve_ts_import(spec: str, from_path: str, repo_root: Path) -> str | None:
    base, aliases = load_tsconfig_paths(repo_root)
    candidate = spec
    for alias, dests in aliases.items():
        prefix = alias.replace("*", "")
        if alias.endswith("*") and spec.startswith(prefix):
            rest = spec[len(prefix) :]
            dest = dests[0].replace("*", rest)
            candidate = dest
            break
        if spec == alias.rstrip("*"):
            candidate = dests[0].replace("*", "")
            break
    if candidate.startswith("."):
        parent = (repo_root / from_path).parent
        target = (parent / candidate).resolve()
    else:
        target = (repo_root / base / candidate).resolve()
    for ext in ("", ".ts", ".tsx", ".js", ".jsx", ".d.ts"):
        p = Path(str(target) + ext) if ext else target
        if p.is_file():
            try:
                return p.relative_to(repo_root.resolve()).as_posix()
            except ValueError:
                return None
    index_dir = target if target.is_dir() else Path(str(target))
    for name in ("index.ts", "index.tsx", "index.js"):
        p = index_dir / name
        if p.is_file():
            try:
                return p.relative_to(repo_root.resolve()).as_posix()
            except ValueError:
                return None
    return None


class TsJsParser(LanguageParser):
    language_name = "typescript"

    def __init__(self, dialect: str = "typescript") -> None:
        self.dialect = dialect
        if dialect == "javascript" and tsjs is not None:
            self._parser = make_parser(tsjs)
            self.language_name = "javascript"
        elif tsts is not None:
            # tree-sitter-typescript exposes language_typescript / language_tsx
            lang_fn = getattr(tsts, "language_tsx", None) if dialect == "tsx" else getattr(
                tsts, "language_typescript", None
            )
            if lang_fn is None:
                lang_fn = getattr(tsts, "language", None)
            if lang_fn is None:
                raise RuntimeError("tree-sitter-typescript missing language()")
            from tree_sitter import Language, Parser

            raw = lang_fn()
            language = raw if isinstance(raw, Language) else Language(raw)
            self._parser = Parser(language)
            self.language_name = "typescript"
        elif tsjs is not None:
            self._parser = make_parser(tsjs)
            self.language_name = "javascript"
        else:
            raise RuntimeError("No JS/TS tree-sitter grammar installed")

    def parse_source(self, ctx: ParseContext) -> GraphBatch:
        batch = GraphBatch()
        tree = parse_tree(self._parser, ctx.source)
        module_node = add_module(batch, ctx)
        self._walk(batch, ctx, tree.root_node, module_node, module_node.props["qualified_name"], None)
        return batch

    def _walk(
        self,
        batch: GraphBatch,
        ctx: ParseContext,
        node: Node,
        container: GraphNode,
        qprefix: str,
        current_fn: GraphNode | None,
    ) -> None:
        for child in node.children:
            t = child.type
            if t in ("class_declaration", "class"):
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
                contains(batch, container, cls)
                heritage = next((c for c in child.children if c.type in ("class_heritage", "extends_clause")), None)
                if heritage:
                    ident = node_text(ctx.source, heritage).replace("extends", "").strip()
                    if ident:
                        batch.add_edge(
                            GraphEdge(type="INHERITS", from_id=cls.id, to_id=f"unresolved:{ident}", props={"base": ident})
                        )
                body = named_child(child, "body")
                if body:
                    self._walk(batch, ctx, body, cls, qn, current_fn)
            elif t in ("function_declaration", "method_definition", "function"):
                name_n = named_child(child, "name")
                name = node_text(ctx.source, name_n) if name_n else None
                if t == "method_definition" and not name:
                    name = node_text(ctx.source, child.children[0]) if child.children else "anonymous"
                if not name:
                    continue
                qn = f"{qprefix}.{name}"
                fn = add_symbol(
                    batch,
                    ctx,
                    label="Function",
                    name=name,
                    qualified_name=qn,
                    start_line=child.start_point[0] + 1,
                    end_line=child.end_point[0] + 1,
                    extra={"is_method": t == "method_definition" or container.label == "Class"},
                )
                contains(batch, container, fn)
                body = named_child(child, "body")
                if body:
                    self._walk(batch, ctx, body, container, qprefix, fn)
            elif t == "lexical_declaration" and current_fn is None:
                for n in walk(child):
                    if n.type == "arrow_function":
                        parent = n.parent
                        name = None
                        if parent and parent.type == "variable_declarator":
                            idn = named_child(parent, "name")
                            if idn:
                                name = node_text(ctx.source, idn)
                        if name:
                            qn = f"{qprefix}.{name}"
                            fn = add_symbol(
                                batch,
                                ctx,
                                label="Function",
                                name=name,
                                qualified_name=qn,
                                start_line=n.start_point[0] + 1,
                                end_line=n.end_point[0] + 1,
                                extra={"is_method": False},
                            )
                            contains(batch, container, fn)
                            body = named_child(n, "body")
                            if body:
                                self._walk(batch, ctx, body, container, qprefix, fn)
            elif t in ("import_statement", "import_declaration"):
                src = None
                for n in walk(child):
                    if n.type == "string":
                        src = node_text(ctx.source, n).strip("'\"")
                        break
                if src:
                    batch.add_edge(
                        GraphEdge(
                            type="IMPORTS",
                            from_id=container.id if container.label == "Module" else container.id,
                            to_id=f"unresolved:{src}",
                            props={"module": src, "raw": node_text(ctx.source, child).strip()},
                        )
                    )
            elif t == "call_expression" and current_fn is not None:
                func = named_child(child, "function")
                if func is not None:
                    callee = node_text(ctx.source, func).strip()
                    batch.add_edge(
                        GraphEdge(
                            type="CALLS",
                            from_id=current_fn.id,
                            to_id=f"unresolved:{callee}",
                            props={"callee": callee},
                        )
                    )
            elif child.child_count:
                self._walk(batch, ctx, child, container, qprefix, current_fn)
