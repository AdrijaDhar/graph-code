# Learned re-ranker — leave-one-repo-out evaluation

Trained on the other repos' co-change-labeled candidates, evaluated on the held-out repo — genuine cross-repo generalization, not re-scoring training data.

- `pairwise` trains on within-query (positive, negative) ranking pairs instead of independent binary relevance, to fix binary logreg/gbt's recall@10 regression (see `graphcode.queries.learned_rerank.train_pairwise_logreg`).
- `pw_tuned` picks pairwise's regularization C via an 80/20 query-level split of *only* the training repos (the held-out test repo is never touched while tuning).
- `blend` feeds the plain pairwise model's ranking into `fuse_rrf` as a third ranked list alongside PPR and semantic, instead of replacing RRF outright.

| Held out | rrf | logreg | gbt | pairwise | pw_tuned | blend | rrf MRR | logreg MRR | gbt MRR | pairwise MRR | pw_tuned MRR | blend MRR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| click (C=0.1) | 0.469 | 0.319 | 0.383 | 0.403 | 0.394 | 0.450 | 0.452 | 0.558 | 0.568 | 0.614 | 0.600 | 0.539 |
| typer (C=1.0) | 0.426 | 0.093 | 0.249 | 0.328 | 0.328 | 0.356 | 0.288 | 0.159 | 0.399 | 0.379 | 0.379 | 0.438 |
| cli (C=10.0) | 0.331 | 0.340 | 0.379 | 0.351 | 0.358 | 0.347 | 0.467 | 0.658 | 0.821 | 0.810 | 0.810 | 0.558 |
