# M2 — retrieval eval (git co-change ground truth)

```bash
python -m eval.retrieval_eval --repo https://github.com/pallets/click --repo https://github.com/tiangolo/typer --repo https://github.com/urfave/cli
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

## Latest results (2026-09-06, 3 repos, 2 languages)

| Repo | lang | queries | file | semantic | structural_bfs | structural_ppr | **hybrid_rrf** |
|---|---|---|---|---|---|---|---|
| pallets/click | Python | 54 | 0.000 | 0.342 | 0.364 | 0.407 | **0.469** |
| tiangolo/typer | Python | 71 | 0.000 | 0.331 | 0.155 | 0.360 | **0.426** |
| urfave/cli | Go | 53 | 0.000 | **0.336** | 0.273 | 0.304 | 0.327 |

**M3's acceptance criterion — hybrid_rrf recall@10 beats both file and semantic — holds
on 2 of 3 repos, not universally.** On the Go repo, `hybrid_rrf` (0.331) is essentially
tied with, and technically just under, `semantic` alone (0.336). Not smoothed over: this
is the real result of adding a 3rd repo specifically to check whether the claim
generalizes, and it doesn't cleanly.

**Update**: the leading hypothesis here was that Go cross-package imports without
go.mod-based resolution left the structural graph sparser for Go than Python — since
tested directly, and the hypothesis doesn't hold. `resolve_imports`/`resolve_calls`
now read go.mod and correctly resolve cross-package calls (verified by a real
multi-file-package unit test, `tests/test_go_import_resolution.py`), but re-running
this exact eval afterward moved the numbers by noise-level amounts (structural_ppr
0.307 → 0.304, hybrid_rrf 0.331 → 0.327) — essentially unchanged. So cross-package
import resolution was real and worth fixing on its own correctness merits (confirmed:
+4 edges on urfave/cli, not the +307 a naive multi-file-fanout version produced and
which measurably *hurt* recall by diluting PPR's random-walk mass — see
`resolver/imports.py::_go_import_paths`), but it was not, in fact, the explanation for
Go's weaker retrieval signal here. The actual cause remains open — take the Python
result as the stronger evidence; the Go result as a genuine, still-unexplained,
language-dependent caveat, not a contradiction to paper over.

Also worth keeping: on a smaller 30-query subsample of click, `structural_ppr` alone
briefly out-scored the fusion; the full 54-query run resolved that into hybrid_rrf
being the clear best there. Small-sample retrieval numbers are noisy generally — one
more reason the Go result above needs a second Go repo before treating it as settled
rather than a single-sample artifact.

Token-budget sweep (`click`, n=20 sampled queries): recall climbs sharply from 0.125
(200 tokens) to 0.521 (1000 tokens) and then **plateaus** — the tiered compiler
(`context/pipeline.py`, M4) reaches near-maximal gold-recall by ~1000 tokens, an order
of magnitude under the old 8000-token default, because Tier 1-3 candidates cost only a
handful of tokens each instead of a full source-code slice. The Go repo shows the same
shape (0.113 → 0.333, plateauing by 1000 tokens) — the compiler's efficiency gain looks
language-independent even where the retrieval ranking result doesn't.

See `results/click.md`, `results/typer.md`, `results/cli.md` for the full per-repo
reports, including the M4 budget table.
