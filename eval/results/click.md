# Retrieval eval — https://github.com/pallets/click

54 queries, ground truth mined from git co-change history (min count 2).

| Method | recall@10 | MRR |
|---|---|---|
| file | 0.000 | 0.000 |
| semantic | 0.342 | 0.442 |
| structural_bfs | 0.364 | 0.326 |
| structural_ppr | 0.407 | 0.598 |
| hybrid_rrf | 0.469 | 0.452 |

**M3 acceptance check**: hybrid_rrf recall@10 (0.469) beats file (0.000) and semantic (0.342).

## M4 — gold-recall per token budget (n=20 sampled queries)

| Budget | Gold files captured (mean recall) |
|---|---|
| 200 | 0.125 |
| 500 | 0.412 |
| 1000 | 0.521 |
| 2000 | 0.521 |
| 4000 | 0.521 |
| 8000 | 0.521 |
