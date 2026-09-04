from __future__ import annotations

from pathlib import Path

from graphcode.parsers.ts_js_parser import resolve_ts_import
from graphcode.schema import GraphBatch, GraphEdge, GraphNode, make_id, module_qid


def _python_module_to_path(mod: str, files: dict[str, str]) -> str | None:
    dotted = mod.replace(".", "/")
    for cand in (f"{dotted}.py", f"{dotted}/__init__.py"):
        if cand in files:
            return cand
    # last segment match
    suffix = dotted.split("/")[-1] + ".py"
    hits = [p for p in files if p.endswith("/" + suffix) or p == suffix]
    return hits[0] if len(hits) == 1 else None


def resolve_imports(batch: GraphBatch, repo_hash: str, repo_root: Path | None = None) -> None:
    modules = {n.props["path"]: n for n in batch.nodes if n.label == "Module"}
    files = {p: n.id for p, n in modules.items()}
    new_edges: list[GraphEdge] = []
    keep: list[GraphEdge] = []
    for e in batch.edges:
        if e.type != "IMPORTS":
            keep.append(e)
            continue
        spec = (e.props or {}).get("module") or ""
        from_mod = next((m for m in batch.nodes if m.id == e.from_id), None)
        path = None
        lang = (from_mod.props.get("language") if from_mod else "") or ""
        if lang == "python":
            path = _python_module_to_path(spec, files)
        elif lang in ("javascript", "typescript") and repo_root is not None and from_mod:
            path = resolve_ts_import(spec, from_mod.props["path"], repo_root)
            if path and path not in files:
                path = None
            if path is None and spec.startswith("."):
                # relative without tsconfig
                src = Path(from_mod.props["path"]).parent
                rel = (src / spec).as_posix()
                for ext in (".ts", ".tsx", ".js", ".jsx"):
                    cand = rel + ext
                    if cand in files:
                        path = cand
                        break
        else:
            # generic: match file stem / path fragment, preferring same-language files
            # to avoid cross-language stem collisions (e.g. Rust "mod util" vs C's util.c/util.h)
            same_lang = [p for p in files if modules[p].props.get("language") == lang]
            search_space = same_lang or list(files)
            spec_clean = spec.strip('<>"')
            mangled = spec_clean.replace("::", "/").replace(".", "/")
            for p in search_space:
                if (
                    p.endswith(spec_clean)
                    or Path(p).name == Path(spec_clean).name
                    or p.endswith(mangled)
                    or Path(p).stem == Path(mangled).stem
                ):
                    path = p
                    break
        if path and path in files:
            new_edges.append(
                GraphEdge(type="IMPORTS", from_id=e.from_id, to_id=files[path], props=e.props)
            )
        else:
            e.props = {**(e.props or {}), "unresolved": True}
            keep.append(e)
    batch.edges = keep + new_edges


def resolve_inherits(batch: GraphBatch) -> None:
    classes = [n for n in batch.nodes if n.label == "Class"]
    by_name: dict[str, list[GraphNode]] = {}
    for c in classes:
        by_name.setdefault(c.props["name"], []).append(c)
    new: list[GraphEdge] = []
    keep: list[GraphEdge] = []
    for e in batch.edges:
        if e.type != "INHERITS":
            keep.append(e)
            continue
        base = (e.props or {}).get("base") or ""
        words = base.split(".")[-1].split("<")[0].strip().split()
        while words and words[0] in ("public", "private", "protected", "virtual"):
            words.pop(0)
        base_name = " ".join(words)
        cands = by_name.get(base_name) or []
        if len(cands) == 1:
            new.append(GraphEdge(type="INHERITS", from_id=e.from_id, to_id=cands[0].id, props=e.props))
        else:
            e.props = {**(e.props or {}), "unresolved": True}
            keep.append(e)
    batch.edges = keep + new
