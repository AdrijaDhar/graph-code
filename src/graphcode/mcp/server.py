from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from graphcode.config import settings
from graphcode.context.compiler import compile_context
from graphcode.context.pipeline import build_context
from graphcode.indexer import get_index_service
from graphcode.queries.call_chain import call_chain
from graphcode.queries.hybrid import semantic_search
from graphcode.queries.paths import blast_radius, shortest_path
from graphcode.watcher.daemon import get_watch

mcp = FastMCP("graph-code")


def _svc():
    return get_index_service()


def _semantic_hits_for(svc, prompt: str, files: list[str] | None, symbols: list[str] | None):
    query_text = prompt or next(iter((symbols or []) + (files or [])), "")
    if not query_text:
        return None
    hits = semantic_search(svc, query_text, k=40)
    return [(h["id"], h["score"]) for h in hits.get("hits") or []]


@mcp.tool()
def graph_index_repo(path: str) -> str:
    """Parse a repository into the code graph and load Memgraph/RocksDB."""
    result = _svc().index_repo(path)
    return json.dumps(result, indent=2)


@mcp.tool()
def graph_status() -> str:
    """Last index time, repo id, counts by label."""
    return json.dumps(_svc().last_index or {"error": "no index yet"}, indent=2)


@mcp.tool()
def graph_shortest_path(from_symbol: str, to_symbol: str, max_hops: int = 10) -> str:
    """Shortest dependency path between two symbols or files."""
    return json.dumps(shortest_path(_svc().memory, from_symbol, to_symbol, max_hops=max_hops), indent=2)


@mcp.tool()
def graph_call_chain(symbol: str, max_depth: int = 5) -> str:
    """Downstream CALLS expansion from a function or file."""
    return json.dumps(call_chain(_svc().memory, symbol, max_depth=max_depth), indent=2)


@mcp.tool()
def graph_blast_radius(symbol_or_file: str, direction: str = "upstream") -> str:
    """Upstream importers/callees or downstream dependencies."""
    return json.dumps(blast_radius(_svc().memory, symbol_or_file, direction=direction), indent=2)


@mcp.tool()
def graph_compile_context(
    prompt: str,
    files: list[str] | None = None,
    symbols: list[str] | None = None,
    max_tokens: int = 8000,
) -> str:
    """Compile structural graph context for an LLM coding agent."""
    svc = _svc()
    root = (svc.last_index or {}).get("root")
    semantic_hits = _semantic_hits_for(svc, prompt, files, symbols)
    return compile_context(
        svc.memory,
        root=root,
        files=files,
        symbols=symbols,
        prompt=prompt,
        max_tokens=max_tokens or settings.max_context_tokens,
        semantic_hits=semantic_hits,
    )


@mcp.tool()
def graph_get_context(
    file: str,
    symbol: str | None = None,
    prompt: str | None = None,
    token_budget: int = 8000,
) -> str:
    """Like graph_compile_context, but through the tiered pipeline contract
    (context/pipeline.py): Tier 0 seed body, Tier 1 direct callers/callees (signature),
    Tier 2 related types (signature), Tier 3 everything else (name only) — packed by
    real token count, not word count. Returns the rendered prompt string."""
    svc = _svc()
    root = (svc.last_index or {}).get("root")
    files = [file] if file else None
    symbols = [symbol] if symbol else None
    semantic_hits = _semantic_hits_for(svc, prompt or "", files, symbols)
    bundle = build_context(
        svc.memory,
        root=root,
        files=files,
        symbols=symbols,
        prompt=prompt or "",
        max_tokens=token_budget or settings.max_context_tokens,
        semantic_hits=semantic_hits,
    )
    return bundle.rendered_prompt


@mcp.tool()
def graph_read_file(path: str) -> str:
    """Read the exact current content of a file in the indexed repo, by path relative
    to the repo root. Use this before proposing an edit to a file so the edit is based
    on real content rather than a guess."""
    root = (_svc().last_index or {}).get("root")
    if not root:
        return "error: no repo indexed yet, call graph_index_repo first"
    root_p = Path(root).resolve()
    target = (root_p / path).resolve()
    if root_p not in target.parents and target != root_p:
        return f"error: path escapes repo root: {path}"
    if not target.is_file():
        return f"error: no such file: {path}"
    if target.stat().st_size > settings.max_file_bytes:
        return f"error: file too large: {path}"
    return target.read_text(encoding="utf-8", errors="replace")


@mcp.tool()
def graph_semantic_search(query: str, k: int = 8) -> str:
    """Embedding kNN over functions, expanded with graph neighbors."""
    return json.dumps(semantic_search(_svc(), query, k=k), indent=2)


@mcp.tool()
def graph_watch_start(path: str) -> str:
    """Start the file-watcher daemon for live reindex."""
    return json.dumps(get_watch().start(path, _svc()), indent=2)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
