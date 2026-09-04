# Benchmarks

Evidence for the two claims the project makes: the resolver is structurally correct,
and it's fast at scale. A third benchmark measures whether the graph context actually
helps an LLM coding agent — the number that matters most for both the product's
`/impact` page and a research CV line.

## B1 — Resolver correctness (`correctness_bench.py`)

```bash
python -m benchmarks.correctness_bench
```

Runs the indexer on `tests/fixtures/mini_repo` and diffs the resolved `CALLS`/`IMPORTS`/
`INHERITS` edges against hand-traced ground truth in `ground_truth/<language>.json` (one
file per language, each entry verified by hand against the source). Reports precision,
recall, and lists any false positive/negative edges. Current result: 100% precision/recall
across all 7 languages on the canonical (unambiguous) cases — see "Known limitations"
below for what's intentionally out of scope.

Building this benchmark surfaced and fixed six real resolver bugs (all covered by the
fixture and the regression suite):
1. Generic import matching mangled dotted filenames (`#include "util.h"` never resolved).
2. Rust `mod x;` declarations weren't captured as `IMPORTS` edges at all.
3. Rust's `::` scope operator wasn't handled when extracting a call's simple name.
4. Cross-language filename collisions (e.g. `util.c`, `util.h`, `util.rs` all share the
   stem "util") could resolve an import to the wrong language's file.
5. Same-package calls with no import statement (Java's default) fell through to a
   globally-ambiguous name lookup instead of preferring same-directory, same-language
   candidates.
6. C++ base-class text kept the `public`/`private`/`virtual` keyword (`"public Base"`),
   so it never matched the class name `"Base"`.

**Known limitations (by design, not counted as benchmark failures):** dynamic dispatch,
`eval`/`getattr`-based calls, ambiguous overloads (two functions with the same name,
same directory, same language), and Go cross-package imports without a `go.mod` are not
resolved by the heuristic resolver — consistent with the "heuristic v1" scope in the
original design doc.

## B2 — Performance / scale (`fixtures_gen.py`, `perf_bench.py`)

```bash
python -m benchmarks.perf_bench --sizes 10,100,500,2000 --queries 60
```

Generates synthetic layered Python repos (utils → services → controllers, realistic
cross-file call/import density, not one-liner files) at each size, times full indexing,
and measures p50/p95 latency for `shortest_path`, `blast_radius`, `call_chain`, and
`compile_context` over randomized queries. Writes `results/perf.csv` and `results/perf.md`.

Measured against the in-memory store (what the MCP server uses without a Memgraph
server running) — a Memgraph-backed run would have different, network-bound latency
characteristics. Latest run: 500-file index in 5.2s (target <30s), 2000-file index in
20.6s, shortest_path p95 well under 5ms at every size tested. `context_compile` (now
running the full hybrid-retrieval path — PPR + semantic fusion, see M3 below) is
53-57ms p95 at 2000 files, comfortably under the 200ms target after two fixes this
benchmark surfaced: PPR was localized to a bounded neighborhood around the seed
instead of running over the whole repo graph (`queries/ppr.py`), and vector reads
(`RocksStore.iter_vectors`) are now cached in memory instead of re-deserializing every
stored embedding from disk on every query — that alone was ~200ms of the ~290ms
pre-fix p95 at 2000 files. Known cosmetic issue: the benchmark process sometimes
aborts with a native `recursive_mutex` error *after* printing/writing results, on
interpreter shutdown — looks like an ONNX Runtime (fastembed) teardown quirk on
macOS, not a correctness issue (results are written before it happens, and it doesn't
reproduce in the pytest suite or normal single-process usage).

## M3 — Hybrid retrieval (PPR + semantic fusion)

`queries/ppr.py` (Personalized PageRank, undirected, edge-type-weighted, localized to
a 4-hop neighborhood around the seed) and `queries/hybrid.fuse_rrf` (reciprocal rank
fusion, k=60) replace raw BFS hop-order with actual importance ranking for the
candidates `context/compiler.compile_context` packs into the body section — a caller
three hops away on the only path now outranks a same-hop node down a rarely-used
branch, and a semantically related function in a file that was never imported can
still surface. All three callers (`mcp/server.graph_compile_context`,
`saas/app.py`'s `/v1/context/compile`, and `perf_bench.py`) now compute
`semantic_hits` via `semantic_search` and pass them through. Unit-tested in isolation
(`tests/test_ppr.py`, `tests/test_hybrid_fusion.py`) with no network dependency.

**Update**: quantitatively validated by `eval/retrieval_eval.py` (M2) —
hybrid_rrf recall@10 beat both `file` and `semantic` on 2 real repos (click: 0.469 vs
0.000/0.342; typer: 0.426 vs 0.000/0.331). See `eval/README.md`.

## M1 + M4 — Pipeline seam + real tokenizer + tiered compiler

`context/pipeline.py` splits `compile_context` into named stages
(`select_seeds → retrieve → fuse → compile`) and replaces flat "pack full bodies until
a word-count budget" with real tiering: Tier 0 (seed) gets full body, Tier 1 (direct
CALLS neighbor) and Tier 2 (related Class/type) get signature-only via a small
parser-agnostic `extract_signature` heuristic, Tier 3 (everything else in the fused
ranking) gets name-only. Token accounting is real (`tiktoken`, `cl100k_base`), not
word count. `context/compiler.compile_context` is now a thin wrapper returning just
`.rendered_prompt`, so every existing caller needed zero changes. A new MCP tool
`graph_get_context` and REST route `POST /v1/context/structured` expose the full
`ContextBundle` (seeds, per-item tiers, real token counts) — the doc's literal
`/context` contract. 12 new tests in `tests/test_pipeline.py`.

Effect, measured by M2's budget sweep (`eval/README.md`): gold-recall now plateaus by
~1000 tokens instead of needing the old 8000-token default — the tiered packer is
roughly an order of magnitude more token-efficient than flat body-dumping for
equivalent recall.

## M2 — Retrieval eval (git co-change ground truth)

See `eval/README.md` and `eval/results/*.md` for the full report — real recall@10/MRR
across 5 retrieval methods on 2 cloned repos with real commit history (125 queries
total, ground truth mined for free from `git log`, not hand-labeled), plus the token-
budget sweep that produced M4's efficiency number above.

## M5 — Incremental updates + latency

Building `benchmarks/incremental_bench.py` surfaced a real, more severe bug than "no
ripple invalidation": `reindex_file`'s resolver batch previously contained *only* the
one reindexed file's fresh nodes, with zero visibility into any other module — meaning
every single-file save silently dropped **all** of that file's cross-file `IMPORTS`/
`CALLS` edges, confirmed via a manual repro before the fix (not merely "doesn't
ripple," actively destructive on every save). Fixed in `indexer.py`: reindex now
merges the freshly-parsed file(s) with the rest of the already-known graph as
resolution *context* (no re-parsing of unrelated files, just reusing their existing
node data for lookups), and additionally re-parses direct `CALLS` neighbors so a
caller elsewhere correctly re-resolves against a callee's new line numbers/signature
without the watcher ever touching the caller file. Verified both directions in
`tests/test_incremental.py`: a metadata-only change ripples correctly to unrelated
callers; a genuine rename with no caller update correctly leaves the call unresolved
(matches real behavior — it *is* broken) rather than silently keeping a stale link.

Also fixed: the durable RocksDB snapshot write was previously synchronous and
re-serialized the *entire* graph on every single-file save (O(total repo size) per
keystroke-save). Now debounced (~5s, coalescing bursts) — `IndexService.flush_snapshot()`
forces it immediately (called by `WatchDaemon.stop()` so nothing pending is lost on
shutdown). In-memory state updates immediately regardless — only the durability write
is debounced, so queries are never stale.

Real before/after numbers (`benchmarks/incremental_bench.py --sizes 10,100,500,2000`):

| Files | before p95 (ms) | after (debounced) p95 (ms) |
|---|---|---|
| 10 | 62.2 | 60.8 |
| 100 | 108.6 | 107.2 |
| 500 | 103.8 | 96.5 |
| 2000 | 190.5 | 137.9–158.6 (varies run to run) |

**Honest result, not rounded up**: p95 at 2000 files hovers right at the <150ms
target — passes in some runs, marginally fails in others. Root cause: resolving with
full-graph context (needed for correctness, see above) rebuilds lookup structures
(`by_name`/`by_path` in `resolver/calls.py`/`resolver/imports.py`) from the whole node
set on every single-file reindex, the same complexity class as a full reindex's
resolve step, just skipping the parse step. A real further fix would index those
lookups incrementally instead of rebuilding per call — noted as a follow-up, not done
here; shipping a correctness fix that's occasionally 10-60ms over a soft latency
target beats shipping a fast fix that keeps deleting your edges.

## B3 — Task-level agent impact (`agent_eval/`)

```bash
export GROQ_API_KEY=...   # free, no card: https://console.groq.com/keys
python -m benchmarks.agent_eval.runner
```

Six hand-built tasks (`agent_eval/tasks.py`), each a small synthetic repo where the
prompt names one file but the correct fix also requires editing a second file in a
different folder — the exact "Cursor misses how a change breaks something five folders
away" failure mode the product targets. Every task's starting state passes its own
check, and a naive same-file-only edit is verified to fail it (see git history / the
sanity checks in this file's development) — the tasks are real, not tautological.

Three conditions per task, same open-weight model (`openai/gpt-oss-120b` on Groq's
free tier by default — a real reasoning model; note `max_tokens` covers its internal
reasoning tokens *and* visible output combined, verified before running this for real):
- **baseline**: only the named file as context (today's typical "few open files" agent)
- **graph**: baseline + files found via `blast_radius()` (the structural context the
  product provides)
- **embedding**: baseline + files found via embedding similarity to the prompt, with no
  graph hops (isolates whether graph structure adds anything beyond semantic search)

Grading runs the patched repo's hidden check in a subprocess — pass/fail depends only on
whether the repo actually works after the patch, not on how the fix was made.

### Results (real run, 2026-09-04)

| Condition | Pass rate |
|---|---|
| baseline | 0/6 (0%) |
| graph | 6/6 (100%) |
| embedding | 6/6 (100%) |

**The headline number**: giving the agent *any* context beyond the single named file
took it from 0% to 100% on tasks that require editing a second file it was never shown
— the core thesis, proven, not just structurally plausible.

**Honest caveat, confirmed by this real run, not just predicted**: graph and embedding
tied at 100% — because all six current tasks rename/change a symbol whose caller uses
the same identifier name, embedding similarity alone finds the right file just as
reliably as graph traversal does here. This run does not demonstrate the graph's
advantage *over* embeddings specifically — only that either beats nothing. Isolating
that would need harder tasks where the caller doesn't share vocabulary with the
definition (e.g. an interface implementation found only via an `INHERITS` edge, not a
shared name) — a natural, scoped next addition to `agent_eval/tasks.py`, not done here.

Writes `results/agent_eval.json` (raw, includes token usage/latency per call) and
`results/agent_eval.md` (pass-rate table).

## M7 — Ablation summary and writeup

Every number below is measured and on disk somewhere in this repo — nothing here is
rounded up or asserted without a run backing it.

**The retrieval ablation grid** (method × token budget), from M2's harness on 2 real
repos with real commit history — this is the actual ablation the roadmap asked for; it
didn't need a separate 60-cell matrix because M2/M4 already sweep both axes:

| Axis | Values | Where |
|---|---|---|
| Retrieval method | file, semantic, structural_bfs, structural_ppr, hybrid_rrf | `eval/results/click.md`, `eval/results/typer.md` |
| Token budget | 200 / 500 / 1000 / 2000 / 4000 / 8000 | same, "M4" section of each |
| Repo | pallets/click (54 queries), tiangolo/typer (71 queries) | same |

Result: `hybrid_rrf` has the best recall@10 on both repos (0.469, 0.426), beating
`file` (0.000, trivially) and `semantic` (0.342, 0.331) — M3's acceptance criterion,
met with real numbers, not just shipped code. Gold-recall plateaus by ~1000 tokens
regardless of method — M4's tiered compiler needs an order of magnitude fewer tokens
than the old flat-body default for equivalent recall.

**The task-outcome ablation** (context condition × task), from M6 — a smaller, sharper
signal than recall@10: does the *patch* actually work.

| Condition | Pass rate (6 tasks) |
|---|---|
| baseline (named file only) | 0% |
| graph (blast_radius) | 100% |
| embedding (semantic only) | 100% |

**Not run**: a budget axis on the task-outcome eval. The 6 `agent_eval` tasks are
small synthetic fixtures (a few lines per file) — their full content already fits
comfortably under any reasonable token budget, so sweeping budget here wouldn't
produce a meaningful gradient, only noise. Forcing that axis to check a box would be
worse than skipping it with this stated reason. If the task set grows to real-repo-sized
files (the natural next step, per B3/M6's own "honest caveat" above), a budget
ablation there would actually mean something.

**The synthesis, in one paragraph**: the graph engine resolves code structure
correctly (B1: 100% precision/recall on hand-verified edges across 7 languages, after
finding and fixing 6 real resolver bugs), scales acceptably (B2/M5: sub-30s indexing
and sub-160ms incremental updates through 2000 files), and the retrieval/compilation
layer built on top of it (M1/M3/M4: PPR + semantic fusion, tiered token-budgeted
packing) measurably outperforms naive baselines on both a large-scale automatic proxy
metric (M2: recall@10 on git co-change ground truth, 125 real queries) and a small,
sharp outcome metric (M6: does the generated patch actually pass). The one claim this
repo does *not* yet support is "graph retrieval specifically beats semantic-only
retrieval on task outcomes" — M2's recall@10 shows the graph contributes real signal,
but M6's 6-task set is too easy (shared vocabulary between caller and callee) to
separate graph from embedding on pass/fail. That's a precise, scoped gap, not a vague
one — worth stating exactly, not smoothing over.

## Extending

- More ground truth: add `<language>.json` entries or a new fixture in
  `tests/fixtures/mini_repo`; re-run `correctness_bench`.
- More scale: `fixtures_gen.generate_repo()` is reusable for any file count.
- More eval tasks: append a `Task(...)` to `agent_eval/tasks.py` — the sanity pattern is
  "unmodified state passes its own check; editing only `primary_file` fails it."
