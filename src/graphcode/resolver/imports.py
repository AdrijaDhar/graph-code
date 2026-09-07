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


def _go_module_path(repo_root: Path | None) -> str | None:
    """Reads the `module <path>` directive from go.mod, if present. Cached by the
    caller (once per resolve_imports call, not per edge) since this hits disk."""
    if repo_root is None:
        return None
    go_mod = repo_root / "go.mod"
    if not go_mod.is_file():
        return None
    for line in go_mod.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("module "):
            return line[len("module ") :].strip()
    return None


def _go_import_paths(spec: str, module_path: str, files: dict[str, str]) -> list[str]:
    """Go imports a *package* (a directory), not a file — `import "mod/pkg/sub"`
    makes every exported identifier in every .go file under that directory available,
    with no per-symbol import list the way Python/JS have. The old generic-fallback
    behavior resolved to at most one file via loose stem matching, silently missing
    calls into any *other* file of the imported package — a real, documented gap
    (eval/README.md: "Go cross-package imports without a go.mod don't resolve").

    Returns exactly one representative file (not every file in the package): emitting
    an edge to every sibling file measurably hurt PPR/blast_radius on a real repo
    (confirmed live on urfave/cli — structural_ppr recall@10 dropped 0.307 -> 0.187
    from just a ~10% edge-count increase, redirecting PPR's random-walk mass away from
    the actually-relevant files). Call *resolution* correctness across the whole
    package is instead handled by resolve_calls.py, which expands this one edge's
    target to its sibling directory when searching for a callee — decoupling "correct
    call resolution" from "structural edge density," which is what the M2 eval
    actually measures. Prefers the file whose name matches the package directory
    (the common `pkg/util/util.go` convention) as the most representative single edge."""
    if not spec.startswith(module_path + "/") and spec != module_path:
        return []  # external (stdlib or third-party) import — no local source to link
    local_dir = spec[len(module_path) :].lstrip("/")
    candidates = [p for p in files if p.endswith(".go") and Path(p).parent.as_posix() == (local_dir or ".")]
    if not candidates:
        return []
    dir_name = Path(local_dir).name if local_dir else ""
    preferred = [p for p in candidates if Path(p).stem == dir_name]
    return [preferred[0]] if preferred else [candidates[0]]


def resolve_imports(batch: GraphBatch, repo_hash: str, repo_root: Path | None = None) -> None:
    modules = {n.props["path"]: n for n in batch.nodes if n.label == "Module"}
    files = {p: n.id for p, n in modules.items()}
    go_module_path = _go_module_path(repo_root)
    new_edges: list[GraphEdge] = []
    keep: list[GraphEdge] = []
    for e in batch.edges:
        if e.type != "IMPORTS":
            keep.append(e)
            continue
        spec = (e.props or {}).get("module") or ""
        from_mod = next((m for m in batch.nodes if m.id == e.from_id), None)
        paths: list[str] = []
        lang = (from_mod.props.get("language") if from_mod else "") or ""
        if lang == "python":
            p = _python_module_to_path(spec, files)
            paths = [p] if p else []
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
            paths = [path] if path else []
        elif lang == "go" and go_module_path:
            paths = _go_import_paths(spec, go_module_path, files)
        if not paths:
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
                    paths = [p]
                    break
        if paths:
            for path in paths:
                if path in files:
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
