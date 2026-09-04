# M2 — retrieval eval (git co-change ground truth)

```bash
python -m eval.retrieval_eval --repo https://github.com/pallets/click --repo https://github.com/tiangolo/typer
```

Ground truth is mined for free from real repo history: if two files were changed
together in the same commit at least twice, they're treated as "should retrieve each
other" (a standard, well-established proxy — not a substitute for `benchmarks/agent_eval`'s
task-pass outcome eval, but automatic and scales to real repos instead of ~6 hand-built
tasks). Clones full history (not `--depth 1` — co-change mining needs commits), so
first run is slower than the shallow clones elsewhere in this repo.

Compares 5 retrieval methods at file granularity — `recall@10` and `MRR` against the
mined gold set — and sweeps token budget through the M4 tiered compiler to report how
much gold-relevant context is captured per token.

## Latest results (2026-09-04)

| Repo | queries | file | semantic | structural_bfs | structural_ppr | **hybrid_rrf** |
|---|---|---|---|---|---|---|
| pallets/click | 54 | 0.000 | 0.342 | 0.364 | 0.407 | **0.469** |
| tiangolo/typer | 71 | 0.000 | 0.331 | 0.155 | 0.360 | **0.426** |

**M3's acceptance criterion — hybrid_rrf recall@10 beats both file and semantic —
holds on both repos.** Honest nuance worth keeping: on a smaller 30-query subsample of
click, `structural_ppr` alone briefly out-scored the fusion; the full 54-query run
resolved that into hybrid_rrf being the clear best. Small-sample retrieval numbers are
noisy — this is why the full run matters, not just a quick subsample.

Token-budget sweep (`click`, n=20 sampled queries): recall climbs sharply from 0.125
(200 tokens) to 0.521 (1000 tokens) and then **plateaus** — the tiered compiler
(`context/pipeline.py`, M4) reaches near-maximal gold-recall by ~1000 tokens, an order
of magnitude under the old 8000-token default, because Tier 1-3 candidates cost only a
handful of tokens each instead of a full source-code slice.

See `results/click.md` and `results/typer.md` for the full per-repo reports, including
the M4 budget table.
