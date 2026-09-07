from __future__ import annotations

from graphcode.loader.memory import MemoryStore
from graphcode.schema import GraphBatch, GraphEdge, GraphNode


def _store() -> MemoryStore:
    """b,c in module "mod"; a (caller, outside) -> b; b -> d (callee, outside)."""
    store = MemoryStore()
    nodes = [
        GraphNode(id="a", label="Function", props={"path": "outside.py", "name": "a"}),
        GraphNode(id="b", label="Function", props={"path": "mod.py", "name": "b"}),
        GraphNode(id="c", label="Function", props={"path": "mod.py", "name": "c"}),
        GraphNode(id="d", label="Function", props={"path": "outside.py", "name": "d"}),
    ]
    edges = [
        GraphEdge(type="CALLS", from_id="a", to_id="b"),
        GraphEdge(type="CALLS", from_id="b", to_id="d"),
        GraphEdge(type="CALLS", from_id="b", to_id="c"),
    ]
    store.load_batch(GraphBatch(nodes=nodes, edges=edges))
    return store


def test_delete_module_removes_its_own_nodes():
    store = _store()
    store.delete_module("mod.py")
    assert "b" not in store.nodes
    assert "c" not in store.nodes
    assert "a" in store.nodes and "d" in store.nodes


def test_delete_module_removes_inbound_edges_from_surviving_callers():
    """a -> b: b is dropped, so a's outgoing edge to b must go too."""
    store = _store()
    store.delete_module("mod.py")
    assert store.out.get("a", []) == []


def test_delete_module_removes_outbound_edges_to_surviving_callees():
    """b -> d: b is dropped, so d's inbound edge from b must go too."""
    store = _store()
    store.delete_module("mod.py")
    assert store.inn.get("d", []) == []


def test_delete_module_removes_edges_between_two_dropped_nodes():
    """b -> c: both dropped; must not leave a dangling edge referencing a gone node."""
    store = _store()
    store.delete_module("mod.py")
    assert "b" not in store.out
    assert "c" not in store.inn


def test_delete_module_leaves_unrelated_edges_untouched():
    store = _store()
    store.nodes["e"] = GraphNode(id="e", label="Function", props={"path": "other.py", "name": "e"})
    store.out["a"].append(GraphEdge(type="CALLS", from_id="a", to_id="e"))
    store.inn["e"].append(store.out["a"][-1])
    store.delete_module("mod.py")
    assert any(e.to_id == "e" for e in store.out.get("a", []))
    assert any(e.from_id == "a" for e in store.inn.get("e", []))


def test_delete_module_noop_for_unknown_path():
    store = _store()
    before_nodes = dict(store.nodes)
    store.delete_module("does/not/exist.py")
    assert store.nodes.keys() == before_nodes.keys()


def test_delete_module_scoped_by_org_id():
    store = MemoryStore()
    store.load_batch(
        GraphBatch(nodes=[GraphNode(id="x", label="Function", props={"path": "m.py"})]), org_id="org1"
    )
    store.load_batch(
        GraphBatch(nodes=[GraphNode(id="y", label="Function", props={"path": "m.py"})]), org_id="org2"
    )
    store.delete_module("m.py", org_id="org1")
    assert "x" not in store.nodes
    assert "y" in store.nodes


def test_find_prefers_dotted_suffix_match_over_unrelated_substring():
    """Regression test for a real, previously-reported bug: querying "feedback" could
    match a stray variable whose qualified_name merely *contains* "feedback" as a
    substring (e.g. a variable inside scripts/export_feedback_csv.py) purely because
    dict iteration reached it first, before the actually-intended function
    `api.app.feedback`. find() must rank a dotted-suffix match (qn ending in
    ".feedback") above a bare substring match, and prefer non-Variable symbols among
    substring matches, regardless of insertion order."""
    store = MemoryStore()
    store.load_batch(
        GraphBatch(
            nodes=[
                # Inserted FIRST deliberately — the old bug was exactly "first loose
                # match wins", so this must still lose despite coming first.
                GraphNode(
                    id="stray_var",
                    label="Variable",
                    props={"path": "scripts/export_feedback_csv.py", "qualified_name": "scripts.export_feedback_csv.raw_feedback"},
                ),
                GraphNode(
                    id="real_fn",
                    label="Function",
                    props={"path": "api/app.py", "qualified_name": "api.app.feedback"},
                ),
            ]
        )
    )
    found = store.find("feedback")
    assert found is not None
    assert found.id == "real_fn"


def test_find_exact_qualified_name_beats_substring_match():
    store = MemoryStore()
    store.load_batch(
        GraphBatch(
            nodes=[
                GraphNode(id="a", label="Function", props={"path": "x.py", "qualified_name": "x.normalize_scores"}),
                GraphNode(id="b", label="Function", props={"path": "y.py", "qualified_name": "normalize"}),
            ]
        )
    )
    found = store.find("normalize")
    assert found is not None
    assert found.id == "b"
