"""M-extra — learned re-ranker: trains a small classifier (logistic regression and
gradient-boosted trees) to replace `hybrid.fuse_rrf`'s fixed RRF weights, using the
same M2 git co-change ground truth (`eval/retrieval_eval.py`) as training labels.
Real, CPU-only, $0 model training that directly extends the existing retrieval eval
rather than being a separate demo.

Evaluated with leave-one-repo-out cross-validation across the same 3 repos M2 already
uses (click, typer, cli): train on 2, test on the 3rd, so the reported numbers are
genuine held-out generalization, not the model re-scoring data it was fit on. The
final model actually saved to disk is trained on all 3 repos combined (the LORO folds
exist to measure whether this approach generalizes at all, not to produce the
production artifact).

Usage:
    python -m eval.train_reranker
    python -m eval.train_reranker --repo https://github.com/pallets/click --repo ...
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

from eval.retrieval_eval import _dedup_files, _mrr, _recall_at_k, K, collect_signals, gather_repo_queries
from graphcode.queries.learned_rerank import (
    FEATURE_NAMES,
    LearnedReranker,
    extract_candidate_features,
    train_gbt,
    train_logreg,
    train_pairwise_logreg,
)

DEFAULT_REPOS = [
    "https://github.com/pallets/click",
    "https://github.com/tiangolo/typer",
    "https://github.com/urfave/cli",
]

MODEL_PATH = Path(__file__).parent.parent / "data" / "models" / "reranker.joblib"
RESULTS_MD = Path(__file__).parent / "results" / "reranker.md"


def precompute_signals(svc, queries: list[tuple[str, set[str]]]) -> dict[str, dict]:
    """Each query's signals (semantic + PPR + BFS) get reused across all 3 LORO folds
    (as training data in 2 folds, as eval data in 1) — computing them once per repo up
    front instead of inside build_examples/score_* avoids 2-3x redundant embedding/PPR
    work across the whole run."""
    return {seed_path: collect_signals(svc, seed_path) for seed_path, _ in queries}


def build_examples(
    svc, queries: list[tuple[str, set[str]]], signals: dict[str, dict]
) -> list[tuple[dict[str, float], int]]:
    """One (feature row, label) example per candidate per query. Label is file-level:
    a candidate node is positive iff its file is in that query's gold co-change set —
    matches the file-granularity recall@10 everything else in this eval is measured on."""
    examples: list[tuple[dict[str, float], int]] = []
    for seed_path, gold in queries:
        sig = signals[seed_path]
        feats = extract_candidate_features(sig["ppr_ranked"], sig["semantic_hits"], sig["bfs_nodes"])
        for nid, row in feats.items():
            node = svc.memory.nodes.get(nid)
            if not node:
                continue
            label = 1 if node.props.get("path") in gold else 0
            examples.append((row, label))
    return examples


def build_pairwise_examples(
    svc,
    queries: list[tuple[str, set[str]]],
    signals: dict[str, dict],
    max_pos: int = 8,
    max_neg: int = 20,
    seed: int = 0,
) -> list[tuple[dict[str, float], int]]:
    """(feature_diff, label) examples from within-query (positive, negative) candidate
    pairs — never across queries, since "more relevant than" is only meaningful
    relative to the same query's candidate set. Capped per query (cross product of all
    positives x negatives would be huge and let queries with many co-changed files
    dominate the loss) and sampled when over the cap, not just truncated, so a query
    with 50 negatives doesn't always contribute the same first 20."""
    rng = random.Random(seed)
    examples: list[tuple[dict[str, float], int]] = []
    for seed_path, gold in queries:
        sig = signals[seed_path]
        feats = extract_candidate_features(sig["ppr_ranked"], sig["semantic_hits"], sig["bfs_nodes"])
        pos_ids, neg_ids = [], []
        for nid in feats:
            node = svc.memory.nodes.get(nid)
            if not node:
                continue
            (pos_ids if node.props.get("path") in gold else neg_ids).append(nid)
        if not pos_ids or not neg_ids:
            continue
        if len(pos_ids) > max_pos:
            pos_ids = rng.sample(pos_ids, max_pos)
        if len(neg_ids) > max_neg:
            neg_ids = rng.sample(neg_ids, max_neg)
        for p in pos_ids:
            for n in neg_ids:
                diff = {name: feats[p][name] - feats[n][name] for name in FEATURE_NAMES}
                examples.append((diff, 1))
                examples.append(({name: -v for name, v in diff.items()}, 0))
    return examples


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def score_with_reranker(svc, queries, signals: dict[str, dict], reranker: LearnedReranker) -> dict[str, float]:
    recalls, mrrs = [], []
    for seed_path, gold in queries:
        sig = signals[seed_path]
        feats = extract_candidate_features(sig["ppr_ranked"], sig["semantic_hits"], sig["bfs_nodes"])
        ranked_ids = reranker.rank(feats)
        ranked_files = _dedup_files(
            [svc.memory.nodes[nid].props.get("path", "") for nid in ranked_ids if nid in svc.memory.nodes]
        )
        recalls.append(_recall_at_k(ranked_files, gold, K))
        mrrs.append(_mrr(ranked_files, gold))
    return {"recall@10": _mean(recalls), "mrr": _mean(mrrs)}


def score_with_reranker_multi(repo_sets: list[tuple], reranker: LearnedReranker) -> dict[str, float]:
    """Like score_with_reranker but pools recall/MRR across several (svc, queries,
    signals) repos — used for C-tuning validation, which spans both training repos."""
    recalls, mrrs = [], []
    for svc, queries, signals in repo_sets:
        for seed_path, gold in queries:
            sig = signals[seed_path]
            feats = extract_candidate_features(sig["ppr_ranked"], sig["semantic_hits"], sig["bfs_nodes"])
            ranked_ids = reranker.rank(feats)
            ranked_files = _dedup_files(
                [svc.memory.nodes[nid].props.get("path", "") for nid in ranked_ids if nid in svc.memory.nodes]
            )
            recalls.append(_recall_at_k(ranked_files, gold, K))
            mrrs.append(_mrr(ranked_files, gold))
    return {"recall@10": _mean(recalls), "mrr": _mean(mrrs)}


def score_rrf_baseline(svc, queries, signals: dict[str, dict]) -> dict[str, float]:
    from graphcode.queries.hybrid import fuse_rrf

    recalls, mrrs = [], []
    for seed_path, gold in queries:
        sig = signals[seed_path]
        structural_ids = [nid for nid, _ in sig["ppr_ranked"]]
        semantic_ids = [nid for nid, _ in sig["semantic_hits"]]
        fused = fuse_rrf(structural_ids, semantic_ids)
        ranked_files = _dedup_files(
            [svc.memory.nodes[nid].props.get("path", "") for nid, _ in fused if nid in svc.memory.nodes]
        )
        recalls.append(_recall_at_k(ranked_files, gold, K))
        mrrs.append(_mrr(ranked_files, gold))
    return {"recall@10": _mean(recalls), "mrr": _mean(mrrs)}


def score_blend(svc, queries, signals: dict[str, dict], reranker: LearnedReranker) -> dict[str, float]:
    """Feeds the learned re-ranker's own ranking into fuse_rrf as a third ranked list
    alongside PPR and semantic, instead of using it as a full replacement — hedges
    between RRF's broad-coverage behavior and the learned model's precision-at-top."""
    from graphcode.queries.hybrid import fuse_rrf

    recalls, mrrs = [], []
    for seed_path, gold in queries:
        sig = signals[seed_path]
        structural_ids = [nid for nid, _ in sig["ppr_ranked"]]
        semantic_ids = [nid for nid, _ in sig["semantic_hits"]]
        feats = extract_candidate_features(sig["ppr_ranked"], sig["semantic_hits"], sig["bfs_nodes"])
        learned_ids = reranker.rank(feats)
        fused = fuse_rrf(structural_ids, semantic_ids, learned_ids)
        ranked_files = _dedup_files(
            [svc.memory.nodes[nid].props.get("path", "") for nid, _ in fused if nid in svc.memory.nodes]
        )
        recalls.append(_recall_at_k(ranked_files, gold, K))
        mrrs.append(_mrr(ranked_files, gold))
    return {"recall@10": _mean(recalls), "mrr": _mean(mrrs)}


C_GRID = (0.01, 0.1, 1.0, 10.0)


def tune_and_train_pairwise(
    train_repo_sets: list[tuple[str, object, list, dict]], val_frac: float = 0.2, seed: int = 42
) -> tuple[LearnedReranker, float]:
    """Picks the pairwise model's regularization strength C via an internal 80/20
    query-level split of the *training* repos only — the held-out LORO test repo is
    never touched during tuning, so picking C this way can't leak test-set answers
    into the "generalizes across repos" claim. Query-level (not example-level) split:
    pairwise examples from the same query are correlated, so splitting examples
    directly would leak query identity across train/val."""
    rng = random.Random(seed)
    tune_train: list = []
    tune_val: list = []
    for name, svc, queries, signals in train_repo_sets:
        shuffled = list(queries)
        rng.shuffle(shuffled)
        n_val = max(1, int(len(shuffled) * val_frac))
        val_q, train_q = shuffled[:n_val], shuffled[n_val:]
        tune_train.append((svc, train_q, signals))
        tune_val.append((svc, val_q, signals))

    best_C, best_recall = 1.0, -1.0
    tune_examples = []
    for svc, train_q, signals in tune_train:
        tune_examples.extend(build_pairwise_examples(svc, train_q, signals))
    for C in C_GRID:
        candidate = LearnedReranker(model=train_pairwise_logreg(tune_examples, C=C), feature_names=FEATURE_NAMES)
        val_scores = score_with_reranker_multi(tune_val, candidate)
        print(f"    C={C:<6} val recall@10={val_scores['recall@10']:.3f} val mrr={val_scores['mrr']:.3f}")
        if val_scores["recall@10"] > best_recall:
            best_recall, best_C = val_scores["recall@10"], C

    print(f"    -> selected C={best_C} (val recall@10={best_recall:.3f}), retraining on full training set")
    full_examples = []
    for name, svc, queries, signals in train_repo_sets:
        full_examples.extend(build_pairwise_examples(svc, queries, signals))
    final = LearnedReranker(model=train_pairwise_logreg(full_examples, C=best_C), feature_names=FEATURE_NAMES)
    return final, best_C


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", action="append", default=None, help="repeatable, default: click+typer+cli")
    ap.add_argument("--min-cochange", type=int, default=2)
    args = ap.parse_args()
    repos = args.repo or DEFAULT_REPOS

    print(f"Indexing {len(repos)} repos and mining co-change queries...")
    per_repo = {}
    for url in repos:
        svc, queries = gather_repo_queries(url, min_cochange=args.min_cochange)
        name = url.rstrip("/").rsplit("/", 1)[-1]
        print(f"  {name}: {len(queries)} queries, computing signals...")
        signals = precompute_signals(svc, queries)
        per_repo[name] = (svc, queries, signals)

    rows = []
    for held_out in per_repo:
        train_examples = []
        pairwise_examples = []
        train_repo_sets = []
        for name, (svc, queries, signals) in per_repo.items():
            if name == held_out:
                continue
            train_examples.extend(build_examples(svc, queries, signals))
            pairwise_examples.extend(build_pairwise_examples(svc, queries, signals))
            train_repo_sets.append((name, svc, queries, signals))
        n_pos = sum(label for _, label in train_examples)
        print(f"\n[fold: held out {held_out}] training on {len(train_examples)} binary examples "
              f"({n_pos} positive, {len(train_examples) - n_pos} negative) and "
              f"{len(pairwise_examples)} pairwise examples from the other repos")

        logreg = LearnedReranker(model=train_logreg(train_examples), feature_names=FEATURE_NAMES)
        gbt = LearnedReranker(model=train_gbt(train_examples), feature_names=FEATURE_NAMES)
        pairwise = LearnedReranker(model=train_pairwise_logreg(pairwise_examples), feature_names=FEATURE_NAMES)
        print("  tuning pairwise C on a held-back slice of the training repos (test repo untouched):")
        pairwise_tuned, best_C = tune_and_train_pairwise(train_repo_sets)

        test_svc, test_queries, test_signals = per_repo[held_out]
        rrf_scores = score_rrf_baseline(test_svc, test_queries, test_signals)
        logreg_scores = score_with_reranker(test_svc, test_queries, test_signals, logreg)
        gbt_scores = score_with_reranker(test_svc, test_queries, test_signals, gbt)
        pairwise_scores = score_with_reranker(test_svc, test_queries, test_signals, pairwise)
        tuned_scores = score_with_reranker(test_svc, test_queries, test_signals, pairwise_tuned)
        blend_scores = score_blend(test_svc, test_queries, test_signals, pairwise)
        print(f"  hybrid_rrf         recall@10={rrf_scores['recall@10']:.3f} mrr={rrf_scores['mrr']:.3f}")
        print(f"  hybrid_logreg      recall@10={logreg_scores['recall@10']:.3f} mrr={logreg_scores['mrr']:.3f}")
        print(f"  hybrid_gbt         recall@10={gbt_scores['recall@10']:.3f} mrr={gbt_scores['mrr']:.3f}")
        print(f"  hybrid_pairwise    recall@10={pairwise_scores['recall@10']:.3f} mrr={pairwise_scores['mrr']:.3f}")
        print(f"  hybrid_pw_tuned(C={best_C}) recall@10={tuned_scores['recall@10']:.3f} mrr={tuned_scores['mrr']:.3f}")
        print(f"  hybrid_blend       recall@10={blend_scores['recall@10']:.3f} mrr={blend_scores['mrr']:.3f}")
        rows.append((held_out, rrf_scores, logreg_scores, gbt_scores, pairwise_scores, tuned_scores, blend_scores, best_C))

    lines = [
        "# Learned re-ranker — leave-one-repo-out evaluation",
        "",
        "Trained on the other repos' co-change-labeled candidates, evaluated on the held-out "
        "repo — genuine cross-repo generalization, not re-scoring training data.",
        "",
        "- `pairwise` trains on within-query (positive, negative) ranking pairs instead of "
        "independent binary relevance, to fix binary logreg/gbt's recall@10 regression "
        "(see `graphcode.queries.learned_rerank.train_pairwise_logreg`).",
        "- `pw_tuned` picks pairwise's regularization C via an 80/20 query-level split of "
        "*only* the training repos (the held-out test repo is never touched while tuning).",
        "- `blend` feeds the plain pairwise model's ranking into `fuse_rrf` as a third "
        "ranked list alongside PPR and semantic, instead of replacing RRF outright.",
        "",
        "| Held out | rrf | logreg | gbt | pairwise | pw_tuned | blend | rrf MRR | logreg MRR | "
        "gbt MRR | pairwise MRR | pw_tuned MRR | blend MRR |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for held_out, rrf_s, lr_s, gbt_s, pw_s, tuned_s, blend_s, best_C in rows:
        lines.append(
            f"| {held_out} (C={best_C}) | {rrf_s['recall@10']:.3f} | {lr_s['recall@10']:.3f} | "
            f"{gbt_s['recall@10']:.3f} | {pw_s['recall@10']:.3f} | {tuned_s['recall@10']:.3f} | "
            f"{blend_s['recall@10']:.3f} | {rrf_s['mrr']:.3f} | {lr_s['mrr']:.3f} | {gbt_s['mrr']:.3f} | "
            f"{pw_s['mrr']:.3f} | {tuned_s['mrr']:.3f} | {blend_s['mrr']:.3f} |"
        )
    report = "\n".join(lines) + "\n"
    RESULTS_MD.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_MD.write_text(report)
    print("\n" + report)

    # C-tuning matched or slightly underperformed the untuned C=1.0 default in every
    # LORO fold above (click: tuning picked a worse C than default; typer/cli: tuning
    # picked C=1.0 anyway, i.e. no-op) — a real, reportable negative result, not
    # something to paper over by quietly using the tuned path for the shipped model.
    # Keep the simpler untuned default here since the evidence doesn't support the
    # extra complexity.
    print("Training final production model (plain pairwise, C=1.0 default — tuning above showed no "
          "reliable benefit) on all repos combined...")
    all_pairwise = []
    for _, (svc, queries, signals) in per_repo.items():
        all_pairwise.extend(build_pairwise_examples(svc, queries, signals))
    final = LearnedReranker(model=train_pairwise_logreg(all_pairwise), feature_names=FEATURE_NAMES)
    final.save(MODEL_PATH)
    print(f"Saved to {MODEL_PATH} ({len(all_pairwise)} pairwise training examples)")


if __name__ == "__main__":
    main()
