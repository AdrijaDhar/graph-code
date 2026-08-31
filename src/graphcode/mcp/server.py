from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from graphcode.config import settings
from graphcode.context.compiler import compile_context
from graphcode.indexer import get_index_service
from graphcode.queries.call_chain import call_chain
from graphcode.queries.hybrid import semantic_search
from graphcode.queries.paths import blast_radius, shortest_path
from graphcode.watcher.daemon import get_watch

mcp = FastMCP("graph-code")


def _svc():
    return get_index_service()


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
    return compile_context(
        svc.memory,
        root=root,
        files=files,
        symbols=symbols,
        prompt=prompt,
        max_tokens=max_tokens or settings.max_context_tokens,
    )


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
