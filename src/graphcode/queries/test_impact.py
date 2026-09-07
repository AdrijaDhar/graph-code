"""Test-impact analysis: given a changed symbol, which tests actually exercise it?

The natural next question after blast_radius answers "what breaks" is "what do I run
to check" — and the graph already has everything needed to answer it: a test function
that (transitively) calls the changed symbol is exactly blast_radius's upstream
traversal, filtered down to nodes that look like tests. No new graph infrastructure,
just a different lens on what's already there.

Deliberately follows only CALLS edges (not IMPORTS/CONTAINS like blast_radius) — a
test file *importing* a module doesn't mean it exercises a specific function in it,
but a test function *calling* it (even transitively, through helpers) does.
"""

from __future__ import annotations

from pathlib import Path

from graphcode.loader.memory import MemoryStore
from graphcode.queries.paths import _node
from graphcode.schema import GraphNode

_TEST_DIR_MARKERS = ("test", "tests", "spec", "__tests__")
_TEST_NAME_PREFIXES = ("test_", "test", "Test")


def is_test_node(node: GraphNode) -> bool:
    """Path- and name-based, deliberately not relying on decorators/attributes
    (`@pytest.fixture`, `#[test]`, `@Test`) since the parser doesn't capture those
    uniformly across all 7 supported languages — path/name conventions are the one
    signal that generalizes: pytest's test_*.py, Go's *_test.go, JUnit's src/test/java
    layout and *Test.java naming, JS/TS's *.test.ts/__tests__/, etc."""
    path = node.props.get("path", "")
    parts = Path(path).parts
    stem = Path(path).stem.lower()
    if any(part.lower() in _TEST_DIR_MARKERS for part in parts):
        return True
    if stem.startswith("test_") or stem.endswith("_test") or stem.endswith(".test") or stem.endswith(".spec"):
        return True
    name = node.props.get("name", "")
    if name.startswith(_TEST_NAME_PREFIXES):
        return True
    return False


def find_affected_tests(
    store: MemoryStore, key: str, org_id: str | None = None, max_depth: int = 8
) -> dict:
    """BFS backward from `key`, following only CALLS edges, stopping at (not past) the
    first test node found on each path — once a test is found, its own callers (if
    any, e.g. a test runner) aren't relevant to report. Non-test callers keep
    expanding until a test is found or max_depth is hit, so a helper function three
    layers deep from the actual test function still gets attributed correctly."""
    origin = store.find(key, org_id=org_id)
    if not origin:
        return {"tests": [], "error": "not found"}

    def in_org(nid: str) -> bool:
        return org_id is None or store.nodes[nid].props.get("org_id") == org_id

    seen = {origin.id}
    frontier = [origin.id]
    tests: list[dict] = []
    depth = 0
    while frontier and depth < max_depth:
        nxt: list[str] = []
        for nid in frontier:
            for e in store.inn.get(nid, []):
                if e.type != "CALLS":
                    continue
                caller = e.from_id
                if caller in seen or caller not in store.nodes or not in_org(caller):
                    continue
                seen.add(caller)
                node = store.nodes[caller]
                if is_test_node(node):
                    rec = _node(node)
                    rec["depth"] = depth + 1
                    tests.append(rec)
                else:
                    nxt.append(caller)
        frontier = nxt
        depth += 1
    tests.sort(key=lambda t: t["depth"])
    return {"origin": _node(origin), "tests": tests}
