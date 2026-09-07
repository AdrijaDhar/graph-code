"""PR-based blast-radius bot: diffs base...head, finds which indexed functions/classes
actually changed, and reports what structurally depends on them — the core "what
breaks if I change this" pitch, delivered where a reviewer already looks: a PR
comment, not a separate tool they have to remember to run.

See `.github/workflows/pr-blast-radius.yml` for the GitHub Action wiring, and
`graphcode pr-comment --help` for standalone/local use.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import httpx

from graphcode.indexer import IndexService
from graphcode.queries.paths import blast_radius
from graphcode.schema import GraphNode

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

MAX_REPORTED_SYMBOLS = 15
MAX_CALLERS_PER_SYMBOL = 10


def changed_line_ranges(repo_root: Path, base_ref: str, head_ref: str) -> dict[str, list[tuple[int, int]]]:
    """Parses `git diff --unified=0`'s hunk headers for changed line ranges per file,
    in the *new* (head) file's own line numbering — matches the line numbers graph
    nodes carry, since the repo is indexed at head, not base. Triple-dot diffs against
    the merge-base, the standard "what does this PR actually change" comparison (not
    every commit base has picked up on its own branch)."""
    diff = subprocess.run(
        ["git", "-C", str(repo_root), "diff", "--unified=0", f"{base_ref}...{head_ref}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    ranges: dict[str, list[tuple[int, int]]] = {}
    current_file: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            current_file = None if path == "/dev/null" else path.removeprefix("b/")
        elif line.startswith("@@ ") and current_file:
            m = _HUNK_RE.match(line)
            if not m:
                continue
            start = int(m.group(1))
            count = int(m.group(2)) if m.group(2) is not None else 1
            if count == 0:
                continue  # pure deletion at this position in the new file — nothing added here to attribute
            ranges.setdefault(current_file, []).append((start, start + count - 1))
    return ranges


def _overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start <= b_end and b_start <= a_end


def changed_symbols(svc: IndexService, ranges: dict[str, list[tuple[int, int]]]) -> list[GraphNode]:
    """Function/Class nodes (already indexed at head) whose own line range overlaps
    any changed line range in their file — i.e. symbols the diff actually touches,
    not just files it touches."""
    out = []
    for node in svc.memory.nodes.values():
        if node.label not in ("Function", "Class"):
            continue
        file_ranges = ranges.get(node.props.get("path", ""))
        if not file_ranges:
            continue
        start = int(node.props.get("start_line") or 0)
        end = int(node.props.get("end_line") or start)
        if any(_overlaps(start, end, r0, r1) for r0, r1 in file_ranges):
            out.append(node)
    return out


def build_comment(
    svc: IndexService,
    changed: list[GraphNode],
    direction: str = "upstream",
    max_hops: int = 3,
) -> str:
    """Renders the PR comment body. Empty string means "nothing worth posting" (no
    changed symbols at all) — callers should skip posting in that case rather than
    spam every PR with a content-free comment."""
    if not changed:
        return ""

    with_callers: list[tuple[GraphNode, list[dict]]] = []
    for node in changed:
        br = blast_radius(svc.memory, node.id, direction=direction, max_hops=max_hops)
        # CONTAINS is structural nesting (a function's own containing module, or a
        # sibling reached only through it), not a usage relationship — every function
        # has a CONTAINS edge from its module, so without this filter every single
        # report would list "the file this function lives in" as a false-positive
        # dependent (confirmed live: this is exactly what test_pr_bot.py caught).
        callers = [
            n for n in (br.get("nodes") or [])
            if n["id"] != node.id and n.get("via") != "CONTAINS"
        ]
        if callers:
            with_callers.append((node, callers))

    lines = [
        "### 🕸️ Blast radius for this PR",
        "",
        "Structural dependency check ([graph-code](https://github.com/AdrijaDhar/graph-code)) — "
        "who calls or imports what this PR changes, found by traversing the real "
        "call/import graph, not text search.",
    ]

    if not with_callers:
        lines.append("")
        lines.append(f"No other indexed symbols depend on the {len(changed)} changed symbol(s) in this PR.")
        lines.append("")
        lines.append("<sub>Posted automatically by graph-code's blast-radius PR check.</sub>")
        return "\n".join(lines)

    with_callers.sort(key=lambda pair: len(pair[1]), reverse=True)
    shown = with_callers[:MAX_REPORTED_SYMBOLS]
    for node, callers in shown:
        qn = node.props.get("qualified_name") or node.props.get("path")
        lines.append("")
        lines.append(f"**`{qn}`** changed — {len(callers)} dependent(s):")
        for c in callers[:MAX_CALLERS_PER_SYMBOL]:
            cname = c.get("qualified_name") or c.get("path")
            lines.append(f"- `{cname}` ({c.get('path')}) via {c.get('via')}")
        if len(callers) > MAX_CALLERS_PER_SYMBOL:
            lines.append(f"- …and {len(callers) - MAX_CALLERS_PER_SYMBOL} more")

    if len(with_callers) > MAX_REPORTED_SYMBOLS:
        lines.append("")
        lines.append(f"…and {len(with_callers) - MAX_REPORTED_SYMBOLS} more changed symbol(s) with dependents "
                      f"not shown here.")

    lines.append("")
    lines.append("<sub>Posted automatically by graph-code's blast-radius PR check.</sub>")
    return "\n".join(lines)


def post_github_comment(repo_slug: str, pr_number: int, body: str, token: str) -> None:
    r = httpx.post(
        f"https://api.github.com/repos/{repo_slug}/issues/{pr_number}/comments",
        json={"body": body},
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        timeout=20,
    )
    r.raise_for_status()
