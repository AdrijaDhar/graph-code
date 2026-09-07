# Graph-Code for VS Code

Blast radius, shortest path, and semantic search over your codebase's **real
call/import graph** (Tree-sitter parsed) — not text search, so it catches a caller
that never mentions the changed symbol's name in its own source.

Fully local: this extension shells out to the [`graphcode`](https://github.com/AdrijaDhar/graph-code)
CLI on your machine. No account, no server, no data leaves your computer.

## Setup

```bash
git clone https://github.com/AdrijaDhar/graph-code
cd graph-code && pip install -e .
```

Make sure `graphcode` is on your `PATH` (activate the venv you installed it into, or
set the `graphcode.command` setting to its full path).

## Use

1. Open a folder, run **Graph-Code: Index Workspace** (also in the status bar).
2. Place your cursor on a function/class name, run **Graph-Code: Blast Radius for
   Symbol at Cursor** (or right-click it) — see everything that depends on it, jump
   straight to any result.
3. **Graph-Code: Semantic Search** — describe what you're looking for in plain
   language when you don't remember the exact name.
4. **Graph-Code: Shortest Path Between Two Symbols** — trace how two things are
   structurally connected.

Re-run **Index Workspace** after significant changes — the graph doesn't auto-update
live yet in this extension (the underlying `graphcode watch` daemon does, for CLI use).
