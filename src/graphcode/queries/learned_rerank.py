"""Learned re-ranker: replaces `hybrid.fuse_rrf`'s fixed reciprocal-rank weights with
weights fit on real data — the M2 git co-change ground truth (`eval/retrieval_eval.py`)
already mined for free from repo history.

RRF's `1/(k + rank)` per list, summed, is a reasonable scale-free default with no
tuning, but it's still a fixed heuristic: it can't learn that, say, "found by both PPR
*and* semantic search" is disproportionately stronger evidence than either alone, or
that raw PPR score matters beyond just rank. A small classifier trained to predict
"is this candidate actually gold-relevant" from each method's rank/score can, and
still runs in microseconds at inference time (this only replaces the *scoring* of an
already-small candidate set, not the retrieval itself).

Training/evaluation lives in `eval/train_reranker.py` (needs the repo-mining/indexing
machinery in `eval/retrieval_eval.py`, which this module deliberately does not import,
to keep the installed library free of eval-script dependencies); this module is just
the feature contract + model wrapper, usable at both training and inference time.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

FEATURE_NAMES = [
    "ppr_rank_score",
    "ppr_raw_score",
    "ppr_raw_score_norm",
    "semantic_rank_score",
    "semantic_raw_score",
    "semantic_raw_score_norm",
    "bfs_hop_score",
    "in_ppr",
    "in_semantic",
    "in_bfs",
    "n_signals",
]

_RRF_K = 60


def extract_candidate_features(
    ppr_ranked: list[tuple[str, float]],
    semantic_hits: list[tuple[str, float]],
    bfs_nodes: list[dict],
) -> dict[str, dict[str, float]]:
    """Unions candidates across all three raw signal sources and computes one feature
    row per candidate node id. Rank-based scores use RRF's own `1/(k+rank+1)` so they
    stay on a scale a linear model can combine sensibly; raw scores are also kept
    since a tree model (or a linear one, given enough data) can use them directly."""
    feats: dict[str, dict[str, float]] = {}

    def row(nid: str) -> dict[str, float]:
        return feats.setdefault(nid, {name: 0.0 for name in FEATURE_NAMES})

    for rank, (nid, score) in enumerate(ppr_ranked):
        r = row(nid)
        r["ppr_rank_score"] = 1.0 / (_RRF_K + rank + 1)
        r["ppr_raw_score"] = float(score)
        r["in_ppr"] = 1.0

    for rank, (nid, score) in enumerate(semantic_hits):
        r = row(nid)
        r["semantic_rank_score"] = 1.0 / (_RRF_K + rank + 1)
        r["semantic_raw_score"] = float(score)
        r["in_semantic"] = 1.0

    for n in bfs_nodes:
        nid = n.get("id")
        if not nid:
            continue
        hop = n.get("hop")
        r = row(nid)
        r["bfs_hop_score"] = 1.0 / (1.0 + hop) if hop is not None else 1.0
        r["in_bfs"] = 1.0

    for r in feats.values():
        r["n_signals"] = r["in_ppr"] + r["in_semantic"] + r["in_bfs"]

    # Raw PPR/semantic scores aren't on a comparable scale across repos of very
    # different sizes (a 50-file repo's PPR mass concentrates very differently than a
    # 2000-file repo's) — a model trained on one repo's raw-score distribution may not
    # transfer to another's. Min-max normalize within *this query's own* candidate set
    # so the feature means "how strong relative to this query's other candidates",
    # which is comparable across repos; rank-based features were already scale-free.
    max_ppr = max((r["ppr_raw_score"] for r in feats.values()), default=0.0)
    max_sem = max((r["semantic_raw_score"] for r in feats.values()), default=0.0)
    for r in feats.values():
        r["ppr_raw_score_norm"] = r["ppr_raw_score"] / max_ppr if max_ppr > 0 else 0.0
        r["semantic_raw_score_norm"] = r["semantic_raw_score"] / max_sem if max_sem > 0 else 0.0

    return feats


def _to_matrix(examples: list[tuple[dict[str, float], int]]) -> tuple[list[list[float]], list[int]]:
    X = [[f.get(name, 0.0) for name in FEATURE_NAMES] for f, _ in examples]
    y = [label for _, label in examples]
    return X, y


def train_logreg(examples: list[tuple[dict[str, float], int]]) -> Any:
    from sklearn.linear_model import LogisticRegression

    X, y = _to_matrix(examples)
    model = LogisticRegression(max_iter=1000, class_weight="balanced")
    model.fit(X, y)
    return model


def train_pairwise_logreg(examples: list[tuple[dict[str, float], int]], C: float = 1.0) -> Any:
    """Trains on (feature_diff, label) pairs — label 1 means 'the candidate this diff
    favors should rank above the other one in the pair', built from within-query
    (positive, negative) candidate pairs (see `eval/train_reranker.py::
    build_pairwise_examples`). No intercept: a zero diff (two equally-scored
    candidates) should sit exactly at the decision boundary, not be biased toward
    either class.

    Why this exists: plain binary classification (`train_logreg`/`train_gbt`) trains
    each candidate's P(relevant) independently, which empirically collapsed onto a
    few very-high-confidence candidates and hurt recall@10 even as MRR improved
    (measured live, `eval/results/reranker.md`) — it optimizes calibration, not
    correct relative ordering across the whole candidate set. A pairwise objective
    trains directly on "is A more relevant than B", which is what actually determines
    rank order, and doesn't require doing anything special at inference time: since
    `w . (a - b) = w.a - w.b`, the exact same learned weight vector scores individual
    candidates by `w . x` and produces a consistent ranking (see `LearnedReranker.score`)."""
    from sklearn.linear_model import LogisticRegression

    X, y = _to_matrix(examples)
    model = LogisticRegression(max_iter=1000, fit_intercept=False, C=C)
    model.fit(X, y)
    return model


def train_gbt(examples: list[tuple[dict[str, float], int]]) -> Any:
    from sklearn.ensemble import GradientBoostingClassifier

    X, y = _to_matrix(examples)
    # No built-in class_weight on GBT; approximate "balanced" via per-sample weights
    # so the (typically large) negative-candidate majority doesn't just win by volume.
    n_pos = sum(y) or 1
    n_neg = len(y) - n_pos or 1
    sample_weight = [len(y) / (2 * n_pos) if label else len(y) / (2 * n_neg) for label in y]
    model = GradientBoostingClassifier(n_estimators=100, max_depth=3, random_state=0)
    model.fit(X, y, sample_weight=sample_weight)
    return model


@dataclass
class LearnedReranker:
    model: Any
    feature_names: list[str]

    def score(self, feats: dict[str, dict[str, float]]) -> dict[str, float]:
        """Uses `decision_function` (the raw pre-sigmoid linear/additive score) rather
        than `predict_proba` — same ranking order for the plain classifiers (sigmoid is
        monotonic), but also the only correct way to score a pairwise-trained model:
        it was fit on feature *differences*, and `w . (a - b) = w.a - w.b` means the
        same weights score individual candidates directly, with no diff needed at
        inference time. `predict_proba` on a raw (non-diff) candidate vector would be
        meaningless for that model."""
        if not feats:
            return {}
        ids = list(feats.keys())
        X = [[feats[nid].get(name, 0.0) for name in self.feature_names] for nid in ids]
        if hasattr(self.model, "decision_function"):
            raw = self.model.decision_function(X)
        else:
            raw = self.model.predict_proba(X)[:, 1]
        return dict(zip(ids, (float(s) for s in raw)))

    def rank(self, feats: dict[str, dict[str, float]]) -> list[str]:
        scored = self.score(feats)
        return [nid for nid, _ in sorted(scored.items(), key=lambda pair: pair[1], reverse=True)]

    def save(self, path: Path | str) -> None:
        import joblib

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": self.model, "feature_names": self.feature_names}, path)

    @classmethod
    def load(cls, path: Path | str) -> "LearnedReranker":
        import joblib

        d = joblib.load(path)
        return cls(model=d["model"], feature_names=d["feature_names"])


DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[3] / "data" / "models" / "reranker.joblib"

_cached: LearnedReranker | None | str = "unloaded"


def get_default_reranker() -> LearnedReranker | None:
    """Lazily loads the model trained by `eval/train_reranker.py` (LORO-evaluated
    results in `eval/results/reranker.md`). Returns None, cached, if the file isn't
    there — a fresh clone won't have it unless someone runs the training script or the
    repo ships it committed, and callers (`context/pipeline.py::retrieve`) already
    treat None as "fall back to plain fuse_rrf", so a missing model is a silent no-op,
    not an error."""
    global _cached
    if _cached == "unloaded":
        try:
            _cached = LearnedReranker.load(DEFAULT_MODEL_PATH)
        except FileNotFoundError:
            _cached = None
    return _cached
