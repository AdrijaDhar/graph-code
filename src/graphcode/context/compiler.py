from __future__ import annotations

from pathlib import Path

from graphcode.loader.memory import MemoryStore


def slice_source(root: Path, path: str, start: int, end: int, budget_lines: int = 40) -> str:
    fp = root / path
    if not fp.is_file():
        return ""
    lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
    s = max(start - 1, 0)
    e = min(end, s + budget_lines)
    body = "\n".join(lines[s:e])
    return f"--- {path} (lines {s + 1}–{e}) ---\n{body}\n"


def compile_context(
    store: MemoryStore,
    *,
    root: Path | str | None,
    files: list[str] | None = None,
    symbols: list[str] | None = None,
    prompt: str = "",
    max_tokens: int = 8000,
    semantic_hits: list[tuple[str, float]] | None = None,
) -> str:
    """Thin, backward-compatible wrapper: real logic lives in context/pipeline.py's
    select_seeds -> retrieve -> fuse -> compile stages. Kept here, returning just the
    rendered string, so every existing caller (mcp/server.py, saas/app.py,
    benchmarks/perf_bench.py) needs zero changes."""
    from graphcode.context.pipeline import build_context

    bundle = build_context(
        store,
        root=root,
        files=files,
        symbols=symbols,
        prompt=prompt,
        max_tokens=max_tokens,
        semantic_hits=semantic_hits,
    )
    return bundle.rendered_prompt
