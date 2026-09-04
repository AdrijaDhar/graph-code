"""Precision/recall of the CALLS/IMPORTS/INHERITS resolver against hand-verified ground truth.

Usage:
    python -m benchmarks.correctness_bench [--repo PATH] [--ground-truth DIR]

Ground truth files (benchmarks/ground_truth/<language>.json) list every edge that
*should* exist in the fixture repo, traced by hand against the source. An edge type
is scored separately so a benchmark reader can see e.g. "CALLS: 92% recall" without
IMPORTS or INHERITS drowning it out.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from graphcode.indexer import IndexService

DEFAULT_REPO = Path(__file__).parent.parent / "tests" / "fixtures" / "mini_repo"
DEFAULT_GT_DIR = Path(__file__).parent / "ground_truth"
DEFAULT_OUT = Path(__file__).parent / "results" / "correctness.md"


@dataclass
class Scoreboard:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    misses: list[str] = field(default_factory=list)
    extras: list[str] = field(default_factory=list)

    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else float("nan")

    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else float("nan")


def _node_index(svc: IndexService) -> dict:
    """(path, name_or_None) -> node id, for resolving ground-truth references."""
    idx: dict[tuple[str, str | None], str] = {}
    for nid, node in svc.memory.nodes.items():
        path = node.props.get("path")
        if node.label == "Module":
            idx[(path, None)] = nid
        else:
            idx[(path, node.props.get("name"))] = nid
    return idx


def _expected_edges(gt_dir: Path, idx: dict) -> set[tuple[str, str, str]]:
    expected: set[tuple[str, str, str]] = set()
    for gt_file in sorted(gt_dir.glob("*.json")):
        data = json.loads(gt_file.read_text())
        for e in data["edges"]:
            from_key = (e["from_path"], e.get("from_name"))
            to_key = (e["to_path"], e.get("to_name"))
            from_id = idx.get(from_key)
            to_id = idx.get(to_key)
            if from_id is None or to_id is None:
                raise ValueError(f"{gt_file.name}: ground truth references missing node {from_key} -> {to_key}")
            expected.add((e["type"], from_id, to_id))
    return expected


def _actual_edges(svc: IndexService) -> set[tuple[str, str, str]]:
    actual: set[tuple[str, str, str]] = set()
    for edges in svc.memory.out.values():
        for e in edges:
            if e.type == "CONTAINS":
                continue
            actual.add((e.type, e.from_id, e.to_id))
    return actual


def run(repo: Path, gt_dir: Path) -> dict[str, Scoreboard]:
    svc = IndexService(rocks_path=Path("/tmp/gc_correctness_bench_rocks"))
    svc.index_repo(repo, parallel=False)
    idx = _node_index(svc)
    expected = _expected_edges(gt_dir, idx)
    actual = _actual_edges(svc)

    def label(edge_type: str) -> str:
        return edge_type

    boards: dict[str, Scoreboard] = defaultdict(Scoreboard)
    for edge in expected | actual:
        etype = edge[0]
        board = boards[label(etype)]
        in_expected = edge in expected
        in_actual = edge in actual
        readable = f"{edge[1]} -> {edge[2]}"
        if in_expected and in_actual:
            board.tp += 1
        elif in_actual and not in_expected:
            board.fp += 1
            board.extras.append(readable)
        elif in_expected and not in_actual:
            board.fn += 1
            board.misses.append(readable)
    return boards


def render_markdown(boards: dict[str, Scoreboard]) -> str:
    lines = ["# Resolver correctness benchmark", ""]
    lines.append("| Edge type | TP | FP | FN | Precision | Recall |")
    lines.append("|---|---|---|---|---|---|")
    total = Scoreboard()
    for etype in sorted(boards):
        b = boards[etype]
        total.tp += b.tp
        total.fp += b.fp
        total.fn += b.fn
        lines.append(f"| {etype} | {b.tp} | {b.fp} | {b.fn} | {b.precision():.0%} | {b.recall():.0%} |")
    lines.append(f"| **overall** | {total.tp} | {total.fp} | {total.fn} | {total.precision():.0%} | {total.recall():.0%} |")
    lines.append("")
    for etype in sorted(boards):
        b = boards[etype]
        if b.misses:
            lines.append(f"**Missed {etype} edges (false negatives):**")
            lines.extend(f"- {m}" for m in b.misses)
        if b.extras:
            lines.append(f"**Unexpected {etype} edges (false positives):**")
            lines.extend(f"- {m}" for m in b.extras)
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    ap.add_argument("--ground-truth", type=Path, default=DEFAULT_GT_DIR)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    boards = run(args.repo, args.ground_truth)
    report = render_markdown(boards)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report)
    print(report)


if __name__ == "__main__":
    main()
