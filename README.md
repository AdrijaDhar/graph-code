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

MCP (Cursor): copy `.cursor/mcp.json` and set `MEMGRAPH_URI` if you use Docker.

Web UI:

```bash
cd apps/web && npm install && npm run dev
```

Sign-in without GitHub OAuth uses a demo user. Set `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` for real OAuth.

## Deploy ($0)

See [deploy/oracle-cloud.md](deploy/oracle-cloud.md). Stack: Oracle Always Free VM (API + Memgraph + RocksDB), Cloudflare Pages (Next.js), Supabase Postgres, Stripe **test** mode.

## MCP tools

`graph_index_repo`, `graph_status`, `graph_shortest_path`, `graph_call_chain`, `graph_blast_radius`, `graph_compile_context`, `graph_semantic_search`, `graph_watch_start`.
