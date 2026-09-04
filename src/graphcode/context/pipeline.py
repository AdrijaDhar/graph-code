"""select_seeds -> retrieve -> fuse -> compile, as separate, unit-testable stages.

`context/compiler.compile_context` is now a thin wrapper around `build_context` here,
returning just `.rendered_prompt` for backward compatibility with every existing
caller. This module is the actual `/context` contract: `ContextBundle` is the
structured request/response shape from the design doc (seeds, used_tokens, tiered
items, rendered_prompt).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import tiktoken

from graphcode.context.compiler import slice_source
from graphcode.loader.memory import MemoryStore
from graphcode.queries.call_chain import call_chain
from graphcode.queries.hybrid import fuse_rrf
from graphcode.queries.paths import blast_radius, shortest_path
from graphcode.queries.ppr import personalized_pagerank

_ENC = tiktoken.get_encoding("cl100k_base")

# Tier 0: the seed itself -> full body.
# Tier 1: a direct CALLS neighbor of a seed -> signature only (docstring/call-site line
#   extraction would need per-language parser support we don't have yet; documented
#   simplification rather than a half-accurate guess).
# Tier 2: a Class/type node among the ranked candidates -> signature only.
# Tier 3: everything else in the fused ranking -> qualified name only.
TIER_LABELS = {0: "seed", 1: "caller/callee", 2: "type", 3: "related"}


@dataclass
class ContextItem:
    qid: str
    path: str
    tier: int
    tokens: int
    text: str


@dataclass
class ContextBundle:
    seeds: list[str]
    used_tokens: int
    items: list[ContextItem] = field(default_factory=list)
    rendered_prompt: str = ""


def count_tokens(text: str) -> int:
    return len(_ENC.encode(text))


def extract_signature(source_lines: list[str], start_line: int, max_chars: int = 200) -> str:
    """Cheap, parser-agnostic signature extraction: first line(s) up to the first
    top-level ':' (Python) or '{' (C-family), skipping colons/braces nested inside
    parens/brackets (type hints, default args) so `def f(x: int) -> dict:` doesn't
    truncate at the parameter's own colon."""
    idx = max(start_line - 1, 0)
    acc = ""
    depth = 0
    for i in range(idx, min(idx + 5, len(source_lines))):
        for ch in source_lines[i]:
            acc += ch
            if ch in "([":
                depth += 1
            elif ch in ")]":
                depth = max(0, depth - 1)
            elif depth == 0 and ch in ":{":
                return acc.strip()[:max_chars]
        acc += "\n"
        if len(acc) > max_chars:
            break
    return acc.strip()[:max_chars]


def select_seeds(
    store: MemoryStore,
    files: list[str] | None,
    symbols: list[str] | None,
    prompt: str,
) -> list[str]:
    keys = list(symbols or []) + list(files or [])
    if not keys and prompt:
        for tok in prompt.replace(",", " ").split():
            if "/" in tok or "." in tok:
                keys.append(tok.strip("`"))
    return keys


def retrieve(
    store: MemoryStore,
    seed_ids: list[str],
    semantic_hits: list[tuple[str, float]] | None = None,
    top: int = 40,
) -> list[str]:
    """PPR from the seed(s), fused with semantic hits via RRF. Returns ranked node ids
    (excluding the seeds themselves)."""
    structural_ids = [nid for nid, _ in personalized_pagerank(store, seed_ids, top=top)]
    semantic_ids = [nid for nid, _ in (semantic_hits or [])]
    if not structural_ids and not semantic_ids:
        return []
    return [nid for nid, _ in fuse_rrf(structural_ids, semantic_ids)]


def _is_direct_call_neighbor(store: MemoryStore, seed_ids: set[str], node_id: str) -> bool:
    for seed_id in seed_ids:
        for e in store.out.get(seed_id, []):
            if e.type == "CALLS" and e.to_id == node_id:
                return True
        for e in store.inn.get(seed_id, []):
            if e.type == "CALLS" and e.from_id == node_id:
                return True
    return False


def _assign_tier(store: MemoryStore, seed_ids: set[str], node_id: str) -> int:
    if node_id in seed_ids:
        return 0
    node = store.nodes.get(node_id)
    if not node:
        return 3
    if _is_direct_call_neighbor(store, seed_ids, node_id):
        return 1
    if node.label == "Class":
        return 2
    return 3


def _read_lines(root: Path, path: str) -> list[str]:
    fp = root / path
    if not fp.is_file():
        return []
    return fp.read_text(encoding="utf-8", errors="replace").splitlines()


def _render_item(store: MemoryStore, root_p: Path | None, node_id: str, tier: int) -> tuple[str, str]:
    """Returns (path, rendered_text)."""
    node = store.nodes[node_id]
    path = node.props.get("path") or ""
    qn = node.props.get("qualified_name") or path or node_id
    start = int(node.props.get("start_line") or 1)
    end = int(node.props.get("end_line") or start + 20)

    if tier == 0:
        if root_p:
            chunk = slice_source(root_p, path, start, end, budget_lines=60)
            if chunk:
                return path, chunk
        return path, f"{qn}\n"

    if tier in (1, 2):
        sig = qn
        if root_p:
            lines = _read_lines(root_p, path)
            if lines:
                sig = extract_signature(lines, start)
        return path, f"- {qn}: {sig}\n"

    return path, f"- {qn}\n"


def compile(
    store: MemoryStore,
    root: Path | str | None,
    seed_ids: list[str],
    ranked_ids: list[str],
    max_tokens: int,
) -> ContextBundle:
    root_p = Path(root) if root else None
    seed_set = set(seed_ids)
    ordered = list(seed_ids) + [nid for nid in ranked_ids if nid not in seed_set]

    items: list[ContextItem] = []
    seen: set[str] = set()
    used = 0
    for nid in ordered:
        if nid in seen or nid not in store.nodes:
            continue
        seen.add(nid)
        tier = _assign_tier(store, seed_set, nid)
        path, text = _render_item(store, root_p, nid, tier)
        tok = count_tokens(text)
        if used + tok > max_tokens:
            node = store.nodes[nid]
            qn = node.props.get("qualified_name") or path or nid
            stub = f"- stub: {qn}\n"
            stub_tok = count_tokens(stub)
            if used + stub_tok <= max_tokens:
                items.append(ContextItem(qid=nid, path=path, tier=3, tokens=stub_tok, text=stub))
                used += stub_tok
            continue
        items.append(ContextItem(qid=nid, path=path, tier=tier, tokens=tok, text=text))
        used += tok

    body = "".join(f"[Tier {it.tier} - {TIER_LABELS[it.tier]}] {it.text}" for it in items)
    return ContextBundle(seeds=seed_ids, used_tokens=used, items=items, rendered_prompt=body)


def build_context(
    store: MemoryStore,
    *,
    root: Path | str | None,
    files: list[str] | None = None,
    symbols: list[str] | None = None,
    prompt: str = "",
    max_tokens: int = 8000,
    semantic_hits: list[tuple[str, float]] | None = None,
) -> ContextBundle:
    keys = select_seeds(store, files, symbols, prompt)
    if not keys:
        return ContextBundle(seeds=[], used_tokens=0, rendered_prompt="## Structural Context\nNo files or symbols provided.\n")

    primary = keys[0]
    seed_node = store.find(primary)
    seed_ids = [seed_node.id] if seed_node else []

    front: list[str] = [f"## Structural Context for: {primary}\n"]
    br = blast_radius(store, primary, direction="upstream", max_hops=3)
    up = br.get("nodes") or []
    front.append(f"### Blast radius (upstream of {primary})\n")
    for n in up[:20]:
        front.append(f"- [{n.get('label')}] {n.get('qualified_name') or n.get('path')} via {n.get('via', 'origin')}\n")
    if len(keys) >= 2:
        sp = shortest_path(store, keys[0], keys[1])
        front.append("\n### Dependency path\n")
        for n in sp.get("path") or []:
            via = n.get("via")
            qn = n.get("qualified_name") or n.get("path")
            front.append(f"{qn}" + (f"  --{via}-->" if via else "") + "\n")
    cc = call_chain(store, primary, max_depth=5)
    front.append("\n### Call chains\n")
    for path in (cc.get("paths") or [])[:5]:
        names = " → ".join(p.get("name") or p.get("qualified_name", "") for p in path)
        front.append(f"- {names}\n")
    front_text = "".join(front)
    front_tokens = count_tokens(front_text)

    if seed_ids:
        ranked = retrieve(store, seed_ids, semantic_hits=semantic_hits, top=40)
    else:
        ranked = [n["id"] for n in up]

    remaining_budget = max(0, max_tokens - front_tokens)
    bundle = compile(store, root, seed_ids or [n["id"] for n in up[:1]], ranked, remaining_budget)

    bundle.rendered_prompt = (
        front_text
        + "\n### Relevant signatures and bodies\n"
        + bundle.rendered_prompt
        + f"\n### Graph summary\n- {len(up) - 1} related nodes within 3 hops\n"
    )
    bundle.used_tokens += front_tokens
    return bundle
