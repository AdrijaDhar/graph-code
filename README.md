# Graph-Code Copilot

Parse a repository with Tree-sitter, store code structure in **Memgraph** (Cypher) plus **RocksDB** snapshots/vectors, and serve dependency context to an LLM agent over **MCP**.

## What it does

- Nodes: Module, Class, Function, Variable
- Edges: CONTAINS, IMPORTS, INHERITS, CALLS
- Queries: shortest path, blast radius, call chains, hybrid semantic search
- File watcher for live reindex
- Mini-SaaS: GitHub login, teams, API keys, usage quotas, admin, public `/impact`

Languages: Python, TypeScript/JavaScript, Go, Java, Rust, C, C++.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
graphcode index tests/fixtures/mini_repo
uvicorn graphcode.saas.app:app --reload --port 8000
```

Optional Memgraph:

```bash
docker compose up -d memgraph
export MEMGRAPH_URI=bolt://localhost:7687
```

MCP agent (built-in, no IDE required):

```bash
export GROQ_API_KEY=...   # free, no card: https://console.groq.com/keys
graphcode chat tests/fixtures/mini_repo
```

Spawns the `graphcode` MCP server as a subprocess, connects over the real MCP protocol
(`src/graphcode/mcp/client.py`), and drives it with a free open-weight model on Groq
doing real tool-calling — the agent decides when to call `graph_blast_radius`,
`graph_read_file`, etc., then proposes changes as a diff you confirm before anything is
written to disk. Any other MCP client (Claude Code, Claude Desktop, etc.) can also
launch `python -m graphcode.mcp.server` directly if you'd rather use one of those.

Web UI (paste any public GitHub URL and try it):

```bash
# terminal 1
uvicorn graphcode.saas.app:app --reload --port 8000
# terminal 2
cd apps/web && npm install && npm run dev
```

Open http://localhost:3000/app — sign-in without GitHub OAuth uses a local demo
account automatically (set `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` for real OAuth).
Paste a GitHub URL (e.g. `https://github.com/httpie/cli`) into "Index a repo" — it's
shallow-cloned into `data/clones/` and indexed. Click into it and use "Load this repo"
before querying: **v1 keeps one repo's graph active in memory at a time** (matches the
project's clear-and-reload design), so switching between repos means re-clicking Load,
not that queries silently return another repo's data.

## Deploy ($0)

See [deploy/oracle-cloud.md](deploy/oracle-cloud.md). Stack: Oracle Always Free VM (API + Memgraph + RocksDB), Cloudflare Pages (Next.js), Supabase Postgres, Stripe **test** mode.

## MCP tools

`graph_index_repo`, `graph_status`, `graph_shortest_path`, `graph_call_chain`, `graph_blast_radius`, `graph_compile_context`, `graph_get_context`, `graph_read_file`, `graph_semantic_search`, `graph_watch_start`.

## Benchmarks

See [benchmarks/README.md](benchmarks/README.md): resolver precision/recall against hand-verified ground truth, index/query performance at scale (including incremental single-file reindex latency), and a task-level eval measuring whether graph context actually improves an LLM agent's success rate on cross-file bug fixes vs. a same-file-only baseline.

See [eval/README.md](eval/README.md): retrieval quality (recall@10, MRR) against ground truth mined for free from real repos' git commit history, comparing file/semantic/structural/hybrid retrieval and sweeping token budget through the tiered context compiler.
