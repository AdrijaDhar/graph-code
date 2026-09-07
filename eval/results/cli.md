# Retrieval eval — https://github.com/urfave/cli

53 queries, ground truth mined from git co-change history (min count 2).

| Method | recall@10 | MRR |
|---|---|---|
| file | 0.000 | 0.000 |
| semantic | 0.336 | 0.565 |
| structural_bfs | 0.273 | 0.368 |
| structural_ppr | 0.304 | 0.449 |
| hybrid_rrf | 0.327 | 0.461 |

**M3 acceptance check**: hybrid_rrf recall@10 (0.327) does NOT beat file (0.000) and semantic (0.336).

## M4 — gold-recall per token budget (n=20 sampled queries)

| Budget | Gold files captured (mean recall) |
|---|---|
| 200 | 0.113 |
| 500 | 0.254 |
| 1000 | 0.333 |
| 2000 | 0.333 |
| 4000 | 0.333 |
| 8000 | 0.333 |
