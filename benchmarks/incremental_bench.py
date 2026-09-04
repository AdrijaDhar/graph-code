"""M5 — single-file reindex latency, against the design doc's <150ms p95 target.

Usage:
    python -m benchmarks.incremental_bench [--sizes 10,100,500] [--touches 30]
"""

from __future__ import annotations

import argparse
import random
import shutil
import tempfile
import time
from pathlib import Path

from benchmarks.fixtures_gen import generate_repo
from graphcode.indexer import IndexService

RESULTS_MD = Path(__file__).parent / "results" / "incremental.md"


def _percentile(samples: list[float], pct: float) -> float:
    if not samples:
        return float("nan")
    s = sorted(samples)
    k = min(len(s) - 1, int(round(pct / 100 * (len(s) - 1))))
    return s[k]


def bench_one_size(n_files: int, n_touches: int, sync_snapshot: bool) -> dict:
    """sync_snapshot=True reproduces the pre-M5 behavior (full snapshot re-save on
    every single-file reindex) for a fair before/after comparison; False is the
    current debounced behavior (what reindex_file actually does today)."""
    root = Path(tempfile.mkdtemp(prefix=f"gc_incr_synth_{n_files}_"))
    generate_repo(root, n_files)
    svc = IndexService(rocks_path=Path(tempfile.mkdtemp(prefix="gc_incr_rocks_")), snapshot_debounce_s=999)
    svc.index_repo(root, parallel=True)

    py_files = [p for p in root.rglob("*.py") if p.name != "__init__.py"]
    rng = random.Random(0)

    latencies = []
    for i in range(n_touches):
        target = rng.choice(py_files)
        rel = target.relative_to(root).as_posix()
        target.write_text(target.read_text() + f"\n# touch {i}\n")
        t0 = time.perf_counter()
        svc.reindex_file(root, rel)
        if sync_snapshot:
            svc.flush_snapshot()
        latencies.append((time.perf_counter() - t0) * 1000)

    shutil.rmtree(root, ignore_errors=True)
    return {
        "files": n_files,
        "touches": n_touches,
        "p50_ms": round(_percentile(latencies, 50), 2),
        "p95_ms": round(_percentile(latencies, 95), 2),
        "max_ms": round(max(latencies), 2),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="10,100,500")
    ap.add_argument("--touches", type=int, default=30)
    args = ap.parse_args()
    sizes = [int(x) for x in args.sizes.split(",")]

    before = [bench_one_size(n, args.touches, sync_snapshot=True) for n in sizes]
    after = [bench_one_size(n, args.touches, sync_snapshot=False) for n in sizes]

    lines = ["# Incremental reindex latency (M5)", ""]
    lines.append(
        "| Files | Touches | before (sync snapshot every save) p50/p95 (ms) | "
        "after (debounced) p50/p95 (ms) |"
    )
    lines.append("|---|---|---|---|")
    for b, a in zip(before, after):
        lines.append(
            f"| {b['files']} | {b['touches']} | {b['p50_ms']}/{b['p95_ms']} | {a['p50_ms']}/{a['p95_ms']} |"
        )
    lines.append("")
    lines.append("Target: p95 < 150ms.")
    for a in after:
        verdict = "PASS" if a["p95_ms"] < 150 else "FAIL"
        lines.append(f"- {a['files']} files (debounced): p95 {a['p95_ms']}ms ({verdict})")
    report = "\n".join(lines) + "\n"

    RESULTS_MD.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_MD.write_text(report)
    print(report)


if __name__ == "__main__":
    main()
