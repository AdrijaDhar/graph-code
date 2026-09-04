from __future__ import annotations

from graphcode.schema import GraphBatch, GraphEdge, GraphNode


def resolve_calls(batch: GraphBatch) -> None:
    functions = [n for n in batch.nodes if n.label == "Function"]
    by_name: dict[str, list[GraphNode]] = {}
    by_qn: dict[str, GraphNode] = {}
    by_path: dict[str, list[GraphNode]] = {}
    for f in functions:
        by_name.setdefault(f.props["name"], []).append(f)
        by_qn[f.props["qualified_name"]] = f
        by_path.setdefault(f.props.get("path", ""), []).append(f)

    imports_by_mod: dict[str, list[str]] = {}
    modules = {n.id: n for n in batch.nodes if n.label == "Module"}
    for e in batch.edges:
        if e.type == "IMPORTS" and not e.to_id.startswith("unresolved:"):
            imports_by_mod.setdefault(e.from_id, []).append(e.to_id)

    new: list[GraphEdge] = []
    keep: list[GraphEdge] = []
    for e in batch.edges:
        if e.type != "CALLS":
            keep.append(e)
            continue
        callee = (e.props or {}).get("callee") or ""
        simple = callee.replace("::", ".").split(".")[-1].split("(")[0].strip()
        src_fn = next((f for f in functions if f.id == e.from_id), None)
        target: GraphNode | None = None
        if src_fn:
            same = [f for f in by_path.get(src_fn.props.get("path", ""), []) if f.props["name"] == simple]
            if len(same) == 1:
                target = same[0]
        if target is None:
            # follow imported modules
            if src_fn:
                parent_mod = next(
                    (
                        m
                        for m in modules.values()
                        if m.props.get("path") == src_fn.props.get("path")
                    ),
                    None,
                )
                if parent_mod:
                    for mid in imports_by_mod.get(parent_mod.id, []):
                        dest = modules.get(mid)
                        if not dest:
                            continue
                        hits = [
                            f
                            for f in functions
                            if f.props.get("path") == dest.props.get("path") and f.props["name"] == simple
                        ]
                        if len(hits) == 1:
                            target = hits[0]
                            break
        if target is None and src_fn:
            # same directory, same language (e.g. Java same-package calls with no import statement)
            src_dir = src_fn.props.get("path", "").rsplit("/", 1)[0]
            src_lang = src_fn.props.get("language")
            hits = [
                f
                for f in functions
                if f.id != e.from_id
                and f.props.get("language") == src_lang
                and f.props.get("path", "").rsplit("/", 1)[0] == src_dir
                and f.props["name"] == simple
            ]
            if len(hits) == 1:
                target = hits[0]
        if target is None:
            hits = by_name.get(simple) or []
            if len(hits) == 1:
                target = hits[0]
        if target is not None and target.id != e.from_id:
            new.append(GraphEdge(type="CALLS", from_id=e.from_id, to_id=target.id, props=e.props))
        else:
            e.props = {**(e.props or {}), "unresolved": True}
            keep.append(e)
    batch.edges = keep + new
