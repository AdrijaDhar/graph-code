"""A second, deliberately dumb MCP server for the live-agent benchmark: only
`list_files`, `read_file`, and `grep` — no graph, no blast radius, no semantic search.
This is what most coding agents actually have today when working on an unfamiliar
codebase (open files + text search), and is the honest baseline `live_runner.py`
measures the graph-tool agent against.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("graph-code-baseline")

_ROOT: Path | None = None


def set_root(path: str) -> None:
    global _ROOT
    _ROOT = Path(path).resolve()


def _resolve(path: str) -> Path:
    assert _ROOT is not None, "call graph_index_repo (set_root) first"
    target = (_ROOT / path).resolve()
    if _ROOT not in target.parents and target != _ROOT:
        raise ValueError(f"path escapes repo root: {path}")
    return target


@mcp.tool()
def graph_index_repo(path: str) -> str:
    """Point the agent at a repo root. Call this first, same contract as the graph
    server's tool of the same name, so both conditions share one setup step."""
    set_root(path)
    return f"ready: {path}"


@mcp.tool()
def list_files(pattern: str = "*") -> str:
    """List repo-relative file paths, optionally filtered by a glob pattern."""
    assert _ROOT is not None
    paths = sorted(str(p.relative_to(_ROOT)) for p in _ROOT.rglob("*") if p.is_file())
    if pattern != "*":
        paths = [p for p in paths if fnmatch.fnmatch(p, pattern)]
    return "\n".join(paths)


@mcp.tool()
def read_file(path: str) -> str:
    """Read the exact current content of a file, by path relative to the repo root."""
    target = _resolve(path)
    if not target.is_file():
        return f"error: no such file: {path}"
    return target.read_text(encoding="utf-8", errors="replace")


@mcp.tool()
def grep(pattern: str, max_results: int = 30) -> str:
    """Case-sensitive substring search across all repo files. Returns
    'path:line: text' per match, this is the only way to find callers/usages
    without a structural graph."""
    assert _ROOT is not None
    hits: list[str] = []
    for p in sorted(_ROOT.rglob("*")):
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if pattern in line:
                hits.append(f"{p.relative_to(_ROOT)}:{i}: {line.strip()}")
                if len(hits) >= max_results:
                    return "\n".join(hits)
    return "\n".join(hits) if hits else "(no matches)"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
