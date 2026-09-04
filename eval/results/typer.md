# Retrieval eval — https://github.com/tiangolo/typer

71 queries, ground truth mined from git co-change history (min count 2).

| Method | recall@10 | MRR |
|---|---|---|
| file | 0.000 | 0.000 |
| semantic | 0.331 | 0.356 |
| structural_bfs | 0.155 | 0.124 |
| structural_ppr | 0.360 | 0.264 |
| hybrid_rrf | 0.426 | 0.288 |

**M3 acceptance check**: hybrid_rrf recall@10 (0.426) beats file (0.000) and semantic (0.331).

## M4 — gold-recall per token budget (n=20 sampled queries)

| Budget | Gold files captured (mean recall) |
|---|---|
| 200 | 0.226 |
| 500 | 0.364 |
| 1000 | 0.451 |
| 2000 | 0.451 |
| 4000 | 0.451 |
| 8000 | 0.451 |
