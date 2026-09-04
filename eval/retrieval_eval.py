"""M2 — retrieval eval against git co-change ground truth, mined for free from real
repo history (no hand-labeling): if two files were changed together in a commit often
enough, they're treated as "should retrieve each other." Standard, well-established
proxy for code-context relevance (not a substitute for M6's patch-pass outcome eval,
but free, automatic, and scales to real repos instead of ~6 hand-built tasks).

Compares 5 retrieval methods at file granularity:
    file            - baseline: nothing but the seed file itself (recall ~0 by construction)
    semantic        - embedding kNN over functions, aggregated to file level
    structural_bfs  - today's blast_radius (unranked BFS)
    structural_ppr  - personalized_pagerank (M3)
    hybrid_rrf      - fuse_rrf(structural_ppr, semantic) (M3's actual fusion)

Usage:
    python -m eval.retrieval_eval --repo https://github.com/pallets/click [--repo ...]
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path

from graphcode.context.pipeline import build_context
from graphcode.indexer import IndexService
from graphcode.queries.hybrid import fuse_rrf, semantic_search
from graphcode.queries.paths import blast_radius
from graphcode.queries.ppr import personalized_pagerank

BUDGETS = (200, 500, 1000, 2000, 4000, 8000)
BUDGET_SAMPLE = 20

CACHE_DIR = Path(tempfile.gettempdir()) / "gc_eval_repos"
RESULTS_DIR = Path(__file__).parent / "results"
K = 10


def ensure_cloned(repo_url: str) -> Path:
    name = repo_url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
    dest = CACHE_DIR / name
    if not dest.exists():
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", repo_url, str(dest)], check=True, capture_output=True)
    return dest


def mine_co_changes(repo_dir: Path, min_count: int = 2, max_files_per_commit: int = 30) -> dict[str, dict[str, int]]:
    log = subprocess.run(
        ["git", "-C", str(repo_dir), "log", "--no-merges", "--name-only", "--pretty=format:__COMMIT__"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    co_changed: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    current: list[str] = []

    def flush():
        if 2 <= len(current) <= max_files_per_commit:
            for a in current:
                for b in current:
                    if a != b:
                        co_changed[a][b] += 1

    for line in log.splitlines():
        if line == "__COMMIT__":
            flush()
            current = []
        elif line.strip():
            current.append(line.strip())
    flush()

    return {f: {o: c for o, c in others.items() if c >= min_count} for f, others in co_changed.items()}


def _dedup_files(paths: list[str]) -> list[str]:
    seen: list[str] = []
    for p in paths:
        if p and p not in seen:
            seen.append(p)
    return seen


def _recall_at_k(ranked: list[str], gold: set[str], k: int) -> float:
    if not gold:
        return 0.0
    return len(set(ranked[:k]) & gold) / len(gold)


def _mrr(ranked: list[str], gold: set[str]) -> float:
    for i, p in enumerate(ranked):
        if p in gold:
            return 1.0 / (i + 1)
    return 0.0


def budget_sweep(svc: IndexService, queries: list[tuple[str, set[str]]], sample: int = BUDGET_SAMPLE) -> dict[int, float]:
    """M4 justification: how much gold-relevant context does the tiered compiler
    capture per token budget? (files whose path appears among the packed items, not
    just listed in the debug 'blast radius' header section)."""
    root = (svc.last_index or {}).get("root")
    sampled = queries[:sample]
    out: dict[int, list[float]] = {b: [] for b in BUDGETS}
    for seed_path, gold in sampled:
        for b in BUDGETS:
            bundle = build_context(svc.memory, root=root, files=[seed_path], max_tokens=b)
            captured = {it.path for it in bundle.items}
            out[b].append(len(captured & gold) / len(gold) if gold else 0.0)
    return {b: (sum(v) / len(v) if v else 0.0) for b, v in out.items()}


def evaluate_repo(repo_url: str, min_cochange: int = 2, max_queries: int = 200) -> dict:
    repo_dir = ensure_cloned(repo_url)
    co_changes = mine_co_changes(repo_dir, min_count=min_cochange)

    svc = IndexService(rocks_path=Path(tempfile.mkdtemp(prefix="gc_eval_rocks_")))
    svc.index_repo(repo_dir, parallel=True)

    modules = {n.props["path"]: n for n in svc.memory.nodes.values() if n.label == "Module"}
    indexed_paths = set(modules)

    queries = []
    for f, others in co_changes.items():
        if f not in indexed_paths:
            continue
        gold = {o for o in others if o in indexed_paths}
        if gold:
            queries.append((f, gold))
    queries = queries[:max_queries]

    scores: dict[str, dict[str, list[float]]] = {
        m: {"recall": [], "mrr": []} for m in ("file", "semantic", "structural_bfs", "structural_ppr", "hybrid_rrf")
    }

    for seed_path, gold in queries:
        seed_node = modules[seed_path]

        hits = semantic_search(svc, seed_node.props.get("qualified_name", seed_path), k=50)
        semantic_ids = [h["id"] for h in hits.get("hits") or []]
        semantic_files = _dedup_files(
            [svc.memory.nodes[nid].props.get("path", "") for nid in semantic_ids if nid in svc.memory.nodes]
        )

        br = blast_radius(svc.memory, seed_path, direction="both", max_hops=3)
        bfs_files = _dedup_files([n.get("path", "") for n in br.get("nodes") or []])

        ppr_ranked = personalized_pagerank(svc.memory, [seed_node.id], top=60)
        structural_ids = [nid for nid, _ in ppr_ranked]
        ppr_files = _dedup_files(
            [svc.memory.nodes[nid].props.get("path", "") for nid in structural_ids if nid in svc.memory.nodes]
        )

        fused = fuse_rrf(structural_ids, semantic_ids)
        hybrid_files = _dedup_files(
            [svc.memory.nodes[nid].props.get("path", "") for nid, _ in fused if nid in svc.memory.nodes]
        )

        per_method = {
            "file": [],
            "semantic": semantic_files,
            "structural_bfs": bfs_files,
            "structural_ppr": ppr_files,
            "hybrid_rrf": hybrid_files,
        }
        for method, ranked in per_method.items():
            scores[method]["recall"].append(_recall_at_k(ranked, gold, K))
            scores[method]["mrr"].append(_mrr(ranked, gold))

    def mean(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    budget_recall = budget_sweep(svc, queries)

    return {
        "repo": repo_url,
        "n_queries": len(queries),
        "methods": {
            m: {"recall@10": mean(v["recall"]), "mrr": mean(v["mrr"])} for m, v in scores.items()
        },
        "budget_recall": budget_recall,
        "budget_sample": min(BUDGET_SAMPLE, len(queries)),
    }


def render_markdown(result: dict) -> str:
    lines = [f"# Retrieval eval — {result['repo']}", ""]
    lines.append(f"{result['n_queries']} queries, ground truth mined from git co-change history (min count 2).")
    lines.append("")
    lines.append("| Method | recall@10 | MRR |")
    lines.append("|---|---|---|")
    for m, s in result["methods"].items():
        lines.append(f"| {m} | {s['recall@10']:.3f} | {s['mrr']:.3f} |")
    lines.append("")
    hybrid = result["methods"]["hybrid_rrf"]["recall@10"]
    file_r = result["methods"]["file"]["recall@10"]
    semantic_r = result["methods"]["semantic"]["recall@10"]
    verdict = "beats" if hybrid > max(file_r, semantic_r) else "does NOT beat"
    lines.append(
        f"**M3 acceptance check**: hybrid_rrf recall@10 ({hybrid:.3f}) {verdict} "
        f"file ({file_r:.3f}) and semantic ({semantic_r:.3f})."
    )
    lines.append("")
    lines.append(f"## M4 — gold-recall per token budget (n={result['budget_sample']} sampled queries)")
    lines.append("")
    lines.append("| Budget | Gold files captured (mean recall) |")
    lines.append("|---|---|")
    for b, r in result["budget_recall"].items():
        lines.append(f"| {b} | {r:.3f} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", action="append", required=True, help="repeatable")
    ap.add_argument("--min-cochange", type=int, default=2)
    args = ap.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    for repo_url in args.repo:
        result = evaluate_repo(repo_url, min_cochange=args.min_cochange)
        report = render_markdown(result)
        name = repo_url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
        (RESULTS_DIR / f"{name}.md").write_text(report)
        print(report)


if __name__ == "__main__":
    main()
