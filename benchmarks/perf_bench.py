"""Index-time and query-latency scaling curve on synthetic repos.

Measures against the targets from the design doc:
    - full index of a 500-file repo   < 30s
    - shortest-path query             < 50ms
    - context compile                 < 200ms

Usage:
    python -m benchmarks.perf_bench [--sizes 10,100,500,2000] [--queries 60]
"""

from __future__ import annotations

import argparse
import csv
import random
import shutil
import statistics
import tempfile
import time
from pathlib import Path

from benchmarks.fixtures_gen import generate_repo
from graphcode.context.compiler import compile_context
from graphcode.indexer import IndexService
from graphcode.queries.call_chain import call_chain
from graphcode.queries.hybrid import semantic_search
from graphcode.queries.paths import blast_radius, shortest_path

RESULTS_CSV = Path(__file__).parent / "results" / "perf.csv"
RESULTS_MD = Path(__file__).parent / "results" / "perf.md"


def _percentile(samples: list[float], pct: float) -> float:
    if not samples:
        return float("nan")
    s = sorted(samples)
    k = min(len(s) - 1, int(round(pct / 100 * (len(s) - 1))))
    return s[k]


def _time_ms(fn) -> float:
    t0 = time.perf_counter()
    fn()
    return (time.perf_counter() - t0) * 1000


def bench_one_size(root: Path, n_files: int, n_queries: int) -> dict:
    svc = IndexService(rocks_path=Path(tempfile.mkdtemp(prefix="gc_perf_rocks_")))
    t0 = time.perf_counter()
    result = svc.index_repo(root, parallel=True)
    index_s = time.perf_counter() - t0

    fn_ids = [nid for nid, n in svc.memory.nodes.items() if n.label == "Function"]
    rng = random.Random(0)

    sp_lat, br_lat, cc_lat, ctx_lat = [], [], [], []
    for _ in range(n_queries):
        if len(fn_ids) < 2:
            break
        a, b = rng.sample(fn_ids, 2)
        sp_lat.append(_time_ms(lambda: shortest_path(svc.memory, a, b, max_hops=10)))
        br_lat.append(_time_ms(lambda: blast_radius(svc.memory, a, direction="both", max_hops=3)))
        cc_lat.append(_time_ms(lambda: call_chain(svc.memory, a, max_depth=5)))

        def _compile(a=a):
            query_text = svc.memory.nodes[a].props.get("qualified_name", a)
            hits = semantic_search(svc, query_text, k=40)
            semantic_hits = [(h["id"], h["score"]) for h in hits.get("hits") or []]
            return compile_context(svc.memory, root=root, symbols=[a], max_tokens=8000, semantic_hits=semantic_hits)

        ctx_lat.append(_time_ms(_compile))

    def stats(xs: list[float]) -> tuple[float, float]:
        return (_percentile(xs, 50), _percentile(xs, 95)) if xs else (float("nan"), float("nan"))

    sp50, sp95 = stats(sp_lat)
    br50, br95 = stats(br_lat)
    cc50, cc95 = stats(cc_lat)
    ctx50, ctx95 = stats(ctx_lat)

    return {
        "files": n_files,
        "indexed_files": result["files"],
        "functions": result["counts"].get("Function", 0),
        "edges": result["counts"].get("edges", 0),
        "index_s": round(index_s, 3),
        "shortest_path_p50_ms": round(sp50, 2),
        "shortest_path_p95_ms": round(sp95, 2),
        "blast_radius_p50_ms": round(br50, 2),
        "blast_radius_p95_ms": round(br95, 2),
        "call_chain_p50_ms": round(cc50, 2),
        "call_chain_p95_ms": round(cc95, 2),
        "context_compile_p50_ms": round(ctx50, 2),
        "context_compile_p95_ms": round(ctx95, 2),
    }


def run(sizes: list[int], n_queries: int) -> list[dict]:
    rows = []
    for n in sizes:
        tmp = Path(tempfile.mkdtemp(prefix=f"gc_perf_synth_{n}_"))
        try:
            generate_repo(tmp, n)
            rows.append(bench_one_size(tmp, n, n_queries))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return rows


def render_markdown(rows: list[dict]) -> str:
    lines = ["# Performance / scale benchmark", ""]
    lines.append(
        "| Files | Functions | Edges | Index (s) | shortest_path p50/p95 (ms) | "
        "blast_radius p50/p95 (ms) | call_chain p50/p95 (ms) | context_compile p50/p95 (ms) |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        lines.append(
            f"| {r['files']} | {r['functions']} | {r['edges']} | {r['index_s']} | "
            f"{r['shortest_path_p50_ms']}/{r['shortest_path_p95_ms']} | "
            f"{r['blast_radius_p50_ms']}/{r['blast_radius_p95_ms']} | "
            f"{r['call_chain_p50_ms']}/{r['call_chain_p95_ms']} | "
            f"{r['context_compile_p50_ms']}/{r['context_compile_p95_ms']} |"
        )
    lines.append("")
    lines.append("Targets: index <30s @500 files, shortest_path <50ms, context_compile <200ms.")
    for r in rows:
        if r["files"] >= 500:
            verdict = "PASS" if r["index_s"] < 30 else "FAIL"
            lines.append(f"- {r['files']}-file index: {r['index_s']}s ({verdict} vs <30s target)")
        verdict_sp = "PASS" if r["shortest_path_p95_ms"] < 50 else "FAIL"
        verdict_ctx = "PASS" if r["context_compile_p95_ms"] < 200 else "FAIL"
        lines.append(
            f"- {r['files']}-file shortest_path p95: {r['shortest_path_p95_ms']}ms ({verdict_sp} vs <50ms), "
            f"context_compile p95: {r['context_compile_p95_ms']}ms ({verdict_ctx} vs <200ms)"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="10,100,500,2000")
    ap.add_argument("--queries", type=int, default=60)
    args = ap.parse_args()
    sizes = [int(x) for x in args.sizes.split(",")]

    rows = run(sizes, args.queries)

    RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    report = render_markdown(rows)
    RESULTS_MD.write_text(report)
    print(report)


if __name__ == "__main__":
    main()
