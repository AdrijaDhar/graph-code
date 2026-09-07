# Graph-Code Copilot

**[Try the live demo →](https://graph-code-web.onrender.com)** (sign in with GitHub —
free-tier hosting, first request after idle takes ~30s to wake up)

Parse a repository with Tree-sitter into a real structural graph (functions, classes,
imports, calls) and answer the question text search and plain RAG can't: **"what
breaks if I change this?"** — plus shortest path, call chains, and hybrid semantic
search, served to any LLM agent over MCP.

## Why

Two questions matter before any PR merges: *"did I break something I don't know
about?"* and *"which tests actually prove I didn't?"* Normally you answer those by
grepping, asking a teammate, or running the entire suite and hoping — all slow, and
the first two are easy to get wrong on a codebase bigger than fits in your head.

This turns that into something that just happens automatically. Open a PR that
changes a function used in 50 places across code you didn't write, and — with zero
setup, before anyone reviews it — a comment lists the real dependents and the real
tests that exercise it, found by actually tracing the call/import graph, not by
guessing. It catches exactly what grep misses: a caller three files away that never
mentions the changed function's name, or a test three calls deep through a helper.
See the [PR bot](#3-pr-bot-automatic-review-comments) section below for it running
live on this repo's own PRs.

**Doesn't git already do this?** No — git has zero concept of a function or a call,
only text diffs; `git blame`/`git diff` tell you *what lines changed*, never *what
depends on them*. GitHub's "Dependency graph" is a different granularity entirely
(package dependencies, not in-repo function calls). The closest existing thing is an
IDE's "Find All References" — real symbol resolution, not text search — but it's a
manual, one-symbol-at-a-time tool sitting in one developer's editor, and it says
nothing about which tests matter. What doesn't really exist anywhere mainstream is
*automatic, aggregated, per-PR* reporting of both blast radius and test impact
together, visible to every reviewer with zero setup — that's the actual gap here, not
a missing git feature.

## What it does

- Nodes: Module, Class, Function, Variable. Edges: CONTAINS, IMPORTS, INHERITS, CALLS.
- Queries: blast radius, shortest path, call chains, hybrid semantic search
- File watcher for live reindex
- Languages: Python, TypeScript/JavaScript, Go, Java, Rust, C, C++

## Install (needed for every path below except the VS Code extension's own install)

```bash
git clone https://github.com/AdrijaDhar/graph-code
cd graph-code
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest   # confirm it's all green before relying on it
```

Everything below works out of the box on the in-process `MemoryStore` + RocksDB
snapshots — Memgraph is optional, only useful if you want to run real Cypher queries
against the graph directly:

```bash
docker compose up -d memgraph
export MEMGRAPH_URI=bolt://localhost:7687
```

## Pick your path

There are five ways to use this, and they are **not equally heavy** — most need
nothing hosted at all:

| You want... | Use... | Hosting needed? |
|---|---|---|
| Your existing AI tool (Claude Code, Claude Desktop, Cursor) to understand your codebase's structure | [MCP server](#1-plug-into-claude-desktop-claude-code-or-cursor) | **None** — spawned locally by your tool |
| A standalone agent that proposes diffs interactively | [`graphcode chat`](#2-standalone-cli-agent) | **None** — runs on your machine |
| Automatic "here's what breaks" comments on PRs | [PR bot](#3-pr-bot-automatic-review-comments) | **None** — runs on GitHub's own CI, not yours |
| Blast radius / semantic search inside VS Code | [VS Code extension](#4-vs-code-extension) | **None** — local install, like any editor extension |
| A hosted web app strangers can try via a browser link | [Web app deploy](#5-hosted-web-app) | **Yes** — the only path that needs you to actually deploy something |

The first four are the low-friction ones: no server to stand up, no account beyond
what you already have. Only the last one is a real infrastructure commitment.

---

## 1. Plug into Claude Desktop, Claude Code, or Cursor

Your existing agent gains `graph_blast_radius`, `graph_shortest_path`,
`graph_semantic_search`, `graph_call_chain`, `graph_compile_context`, and
`graph_read_file` as tools it can call on its own while it works — no separate app to
run, no server to host. Your AI tool spawns `graphcode mcp-server` itself, as a local
subprocess, exactly like it would spawn any other local MCP server.

Find your venv's `graphcode` binary first (MCP hosts don't inherit your shell PATH,
so this needs to be an absolute path):

```bash
which graphcode   # e.g. /Users/you/graph-code/.venv/bin/graphcode
```

**Claude Desktop** — add to `claude_desktop_config.json` (Settings → Developer → Edit
Config):

```json
{
  "mcpServers": {
    "graph-code": {
      "command": "/absolute/path/to/.venv/bin/graphcode",
      "args": ["mcp-server"]
    }
  }
}
```

**Claude Code** — from the repo you want it to understand:

```bash
claude mcp add graph-code /absolute/path/to/.venv/bin/graphcode -- mcp-server
```

**Cursor** — add to `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (global):
same JSON shape as Claude Desktop above.

Restart the host, then ask it to call `graph_index_repo` on the repo path once per
session (the graph lives in memory, so it needs indexing after each restart) — after
that, ask normal questions ("what breaks if I change X") and the agent reaches for
these tools itself when they're relevant, same as any other tool it has.

## 2. Standalone CLI agent

```bash
export GROQ_API_KEY=...   # free, no card: https://console.groq.com/keys
graphcode chat tests/fixtures/mini_repo
```

Spawns the `graphcode` MCP server as a subprocess, connects over the real MCP protocol
(`src/graphcode/mcp/client.py`), and drives it with a free open-weight model on Groq
doing real tool-calling — the agent decides when to call `graph_blast_radius`,
`graph_read_file`, etc., then proposes changes as a diff you confirm before anything is
written to disk.

Verified live end-to-end (real Groq calls, real repo): asked it to rename a function in
`utils.py`, and it correctly proposed the rename **and** the caller's updated import +
call site in a different file — the actual cross-file behavior this project targets.
Getting there surfaced and fixed real integration bugs, not just the happy path: Groq
rejects the *entire* request server-side if the model hallucinates a tool name (caught
and retried with the valid names instead of crashing), a large tool result can push a
single request over Groq's free-tier request-size cap (individual tool results are now
truncated), the free tier's 8000-tokens-per-minute budget is a rolling window that a
multi-tool-call turn can exhaust mid-conversation (now backed off and retried instead
of crashing), and a closed/piped stdin during the apply-diff confirmation prompt used
to crash with a raw `EOFError` instead of just skipping the file. All covered by
`tests/test_mcp_client.py`. Practical note: on the free tier this reasoning model's
8000 TPM budget is tight enough that a complex multi-file task may need a couple of
tries or hit the round limit — the system prompt caps tool calls at 3 per turn to fit
inside it.

## 3. PR bot (automatic review comments)

A GitHub Action that diffs a PR, finds which indexed functions/classes the diff
actually touches, and comments the real callers/importers of each — using the
structural graph, not text search, so it catches a caller that never mentions the
changed symbol's name in its own diff. It also answers the natural follow-up
question: which tests actually exercise the changed code (traced through CALLS
edges, transitively through helpers — not by filename convention), so the comment
tells you what to run, not just what might break.

**No deployment, ever.** It's a workflow file that runs entirely on GitHub's own CI
infrastructure — not a server you or anyone else hosts. Listed on the
[GitHub Marketplace](https://github.com/marketplace/actions/graph-code-blast-radius)
— find it by name, or add it directly. Two ways to add it, easiest first:

**As a reusable action** (`action.yml`, at the root of this repo) — paste this into
`.github/workflows/pr-blast-radius.yml` in *any* repo, yours or anyone else's:

```yaml
name: blast-radius-comment
on:
  pull_request:
    types: [opened, synchronize, reopened]
permissions:
  pull-requests: write
jobs:
  comment:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # needed: diffs against origin/<base> by name, and blast
                            # radius needs real repo structure, not a shallow clone
      - uses: AdrijaDhar/graph-code@v1
```

That's the whole thing — Python setup, installing `graphcode`, and the `pr-comment
--post` invocation all happen inside the action itself
([`action.yml`](action.yml)). Open a pull request, wait about a minute, see the
comment.

**Or, if you want to see every step explicitly** (what the action above expands to
under the hood — useful if you want to change `--direction` or debug something):

```yaml
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install "graphcode @ git+https://github.com/AdrijaDhar/graph-code.git"
      - run: >
          graphcode pr-comment --repo . --base origin/${{ github.base_ref }}
          --head HEAD --post
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
```

Try it locally first, against any two refs in any repo (prints the comment instead of
posting it — add `--post` with `GITHUB_TOKEN`/`GITHUB_REPOSITORY`/`PR_NUMBER` set to
actually comment):

```bash
graphcode pr-comment --repo . --base origin/main --head HEAD
```

## 4. VS Code extension

Blast radius, shortest path, and semantic search from inside the editor — right-click
a symbol, or use the Command Palette. Lives in [`vscode-extension/`](vscode-extension/).

**No deployment** — same as the Python or ESLint extensions, this is a local install
that reads *your* local code by shelling out to the `graphcode` CLI on your machine
(the `pip install` from the top of this README, already done if you're following
along in order). Two ways to get it:

**Right now, locally** — a packaged `.vsix` is already built:

```bash
code --install-extension vscode-extension/graph-code-0.1.0.vsix
```

(No `code` CLI? Open VS Code → Extensions view → `...` menu → *Install from VSIX*.)

**From the Marketplace** (once published — gives real install-count stats, not
needed just to try it yourself):

```bash
ext install adrijadhar.graph-code
```

Once installed: open a folder, run **Graph-Code: Index Workspace** (also sits in the
status bar), then right-click any symbol for **Blast Radius for Symbol at Cursor** or
**Affected Tests for Symbol at Cursor** — the latter tells you which tests actually
exercise it, traced through the real call graph, not filename guessing — or reach for
**Graph-Code: Semantic Search** / **Shortest Path** from the Command Palette. Every
result is a jump-to-location QuickPick.

## 5. Hosted web app

**Live**: [graph-code-web.onrender.com](https://graph-code-web.onrender.com) — sign in
with GitHub and try it against a real repo. Free-tier hosting, so the first request
after a quiet period takes ~30s to wake up; after that it's normal speed.

The one path that's an actual infrastructure commitment — you're standing up a public
URL, not just running something locally.

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

**To actually make that URL public**, pick one:
- [deploy/render.md](deploy/render.md) — **recommended**, simplest: free HTTPS
  subdomain out of the box, no VM/domain/TLS setup. Trade-off: the free tier sleeps
  after 15 minutes idle.
- [deploy/oracle-cloud.md](deploy/oracle-cloud.md) — Oracle Always-Free VM, stays up
  permanently, but you manage Docker/Caddy/DNS yourself and need a domain.

No payment tier required either way — every plan in `saas/usage.py` is priced at $0;
Stripe is entirely optional and only relevant if you later want to charge for it.

---

## MCP tools

`graph_index_repo`, `graph_status`, `graph_shortest_path`, `graph_call_chain`, `graph_blast_radius`, `graph_affected_tests`, `graph_compile_context`, `graph_get_context`, `graph_read_file`, `graph_semantic_search`, `graph_watch_start`.

`graph_affected_tests` answers the natural follow-up to blast radius: not just what breaks, but what to run to check. It traces CALLS edges backward from a symbol — transitively, through helpers — to any indexed test function that exercises it, rather than guessing from filenames. The PR bot uses this automatically (see below); it's also available directly via `graphcode query affected-tests <symbol>` or the VS Code extension's **Affected Tests for Symbol at Cursor** command.

## Benchmarks

See [benchmarks/README.md](benchmarks/README.md): resolver precision/recall against hand-verified ground truth, index/query performance at scale (including incremental single-file reindex latency), and a task-level eval measuring whether graph context actually improves an LLM agent's success rate on cross-file bug fixes vs. a same-file-only baseline.

See [eval/README.md](eval/README.md): retrieval quality (recall@10, MRR) against ground truth mined for free from real repos' git commit history, comparing file/semantic/structural/hybrid retrieval and sweeping token budget through the tiered context compiler.

See [eval/results/reranker.md](eval/results/reranker.md): a learned re-ranker (trained on the same git co-change labels) evaluated with leave-one-repo-out cross-validation — genuine cross-repo generalization, with an honestly-reported case where hyperparameter tuning didn't help. Off by default (`ENABLE_LEARNED_RERANK=true` to opt in) since it's a real research result with real per-repo trade-offs, not something that should silently change every query's ranking.

## License

MIT — see [LICENSE](LICENSE).
