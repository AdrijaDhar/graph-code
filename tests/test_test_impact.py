from __future__ import annotations

from pathlib import Path

from graphcode.indexer import IndexService
from graphcode.loader.memory import MemoryStore
from graphcode.queries.test_impact import find_affected_tests, is_test_node
from graphcode.schema import GraphBatch, GraphEdge, GraphNode


def test_is_test_node_recognizes_common_conventions_across_languages():
    cases = [
        ("tests/test_utils.py", "test_parse", True),
        ("src/utils_test.go", "TestParse", True),
        ("src/main/java/App.java", "run", False),
        ("src/test/java/AppTest.java", "testRun", True),
        ("src/App.test.ts", "checksSomething", True),
        ("__tests__/app.spec.ts", "checksSomething", True),
        ("src/api/app.py", "feedback", False),
    ]
    for path, name, expected in cases:
        node = GraphNode(id="x", label="Function", props={"path": path, "name": name})
        assert is_test_node(node) is expected, f"{path}::{name} expected {expected}"


def _store_with_indirection() -> MemoryStore:
    """test_run (in tests/test_app.py) -> helper (in app/support.py) -> target
    (in app/core.py). Also an unrelated caller of target that is NOT a test, to make
    sure it's correctly excluded and doesn't get mistaken for one."""
    store = MemoryStore()
    nodes = [
        GraphNode(id="target", label="Function", props={"path": "app/core.py", "name": "process", "qualified_name": "app.core.process"}),
        GraphNode(id="helper", label="Function", props={"path": "app/support.py", "name": "helper", "qualified_name": "app.support.helper"}),
        GraphNode(id="test_run", label="Function", props={"path": "tests/test_app.py", "name": "test_run", "qualified_name": "tests.test_app.test_run"}),
        GraphNode(id="prod_caller", label="Function", props={"path": "app/api.py", "name": "handle", "qualified_name": "app.api.handle"}),
    ]
    edges = [
        GraphEdge(type="CALLS", from_id="helper", to_id="target"),
        GraphEdge(type="CALLS", from_id="test_run", to_id="helper"),
        GraphEdge(type="CALLS", from_id="prod_caller", to_id="target"),
    ]
    store.load_batch(GraphBatch(nodes=nodes, edges=edges))
    return store


def test_find_affected_tests_through_indirection():
    store = _store_with_indirection()
    result = find_affected_tests(store, "app.core.process")
    test_ids = {t["id"] for t in result["tests"]}
    assert "test_run" in test_ids
    assert "prod_caller" not in test_ids  # a real caller, but not a test


def test_find_affected_tests_reports_depth():
    store = _store_with_indirection()
    result = find_affected_tests(store, "app.core.process")
    hit = next(t for t in result["tests"] if t["id"] == "test_run")
    assert hit["depth"] == 2  # target <- helper (1) <- test_run (2)


def test_find_affected_tests_no_callers_returns_empty():
    store = MemoryStore()
    store.load_batch(GraphBatch(nodes=[GraphNode(id="lonely", label="Function", props={"path": "a.py", "name": "lonely"})]))
    result = find_affected_tests(store, "lonely")
    assert result["tests"] == []


def test_find_affected_tests_unknown_symbol_returns_error():
    store = MemoryStore()
    result = find_affected_tests(store, "does_not_exist")
    assert result["tests"] == []
    assert "error" in result


def test_find_affected_tests_scoped_by_org_id():
    store = MemoryStore()
    store.load_batch(
        GraphBatch(
            nodes=[
                GraphNode(id="target", label="Function", props={"path": "a.py", "name": "target"}),
                GraphNode(id="test_a", label="Function", props={"path": "tests/test_a.py", "name": "test_a"}),
            ],
            edges=[GraphEdge(type="CALLS", from_id="test_a", to_id="target")],
        ),
        org_id="org1",
    )
    store.load_batch(
        GraphBatch(nodes=[GraphNode(id="target2", label="Function", props={"path": "a.py", "name": "target"})]),
        org_id="org2",
    )
    result = find_affected_tests(store, "target", org_id="org2")
    assert result["tests"] == []  # org2's "target" has no callers; org1's test must not leak in


def test_find_affected_tests_end_to_end_on_real_indexed_repo(tmp_path):
    """Real parsing, real CALLS resolution, not a constructed graph — proves the
    feature works through the actual indexing pipeline, not just against hand-built
    fixtures."""
    root = tmp_path / "repo"
    (root / "app").mkdir(parents=True)
    (root / "tests").mkdir(parents=True)
    (root / "app" / "__init__.py").write_text("")
    (root / "app" / "core.py").write_text("def process(x):\n    return x * 2\n")
    (root / "app" / "support.py").write_text(
        "from app.core import process\n\n\ndef helper(x):\n    return process(x) + 1\n"
    )
    (root / "tests" / "__init__.py").write_text("")
    (root / "tests" / "test_app.py").write_text(
        "from app.support import helper\n\n\ndef test_helper():\n    assert helper(1) == 3\n"
    )

    svc = IndexService(rocks_path=tmp_path / "rocks")
    svc.index_repo(root, parallel=False)

    result = find_affected_tests(svc.memory, "app.core.process")
    test_names = {t.get("qualified_name") or t.get("name") for t in result["tests"]}
    assert any("test_helper" in n for n in test_names)
