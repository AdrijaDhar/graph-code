from __future__ import annotations

from graphcode.context.pipeline import (
    ContextBundle,
    _assign_tier,
    build_context,
    compile,
    count_tokens,
    extract_signature,
    retrieve,
    select_seeds,
)
from graphcode.loader.memory import MemoryStore
from graphcode.schema import GraphBatch, GraphEdge, GraphNode


def _store() -> MemoryStore:
    """seed -CALLS-> callee; seed's class Base <-INHERITS- Child; unrelated leaf."""
    store = MemoryStore()
    nodes = [
        GraphNode(id="seed", label="Function", props={"name": "seed", "qualified_name": "m.seed", "path": "a.py"}),
        GraphNode(id="callee", label="Function", props={"name": "callee", "qualified_name": "m.callee", "path": "b.py"}),
        GraphNode(id="cls_base", label="Class", props={"name": "Base", "qualified_name": "m.Base", "path": "a.py"}),
        GraphNode(id="cls_child", label="Class", props={"name": "Child", "qualified_name": "m.Child", "path": "c.py"}),
        GraphNode(id="distant", label="Function", props={"name": "distant", "qualified_name": "m.distant", "path": "d.py"}),
    ]
    edges = [
        GraphEdge(type="CALLS", from_id="seed", to_id="callee"),
        GraphEdge(type="INHERITS", from_id="cls_child", to_id="cls_base"),
        GraphEdge(type="CALLS", from_id="distant", to_id="distant"),  # keep distant reachable, not seed-adjacent
    ]
    store.load_batch(GraphBatch(nodes=nodes, edges=edges))
    return store


def test_select_seeds_from_symbols_and_files():
    store = _store()
    assert select_seeds(store, files=["a.py"], symbols=["m.seed"], prompt="") == ["m.seed", "a.py"]


def test_select_seeds_falls_back_to_prompt_tokens():
    store = _store()
    assert select_seeds(store, files=None, symbols=None, prompt="fix src/utils.py please") == ["src/utils.py"]


def test_extract_signature_python_stops_at_top_level_colon():
    lines = ["def f(x: int, y: dict = {}) -> str:", "    return str(x)"]
    assert extract_signature(lines, 1) == "def f(x: int, y: dict = {}) -> str:"


def test_extract_signature_c_family_stops_at_brace():
    lines = ["int compute(int x) {", "    return x * 2;"]
    assert extract_signature(lines, 1) == "int compute(int x) {"


def test_tier_assignment_seed_is_tier_0():
    store = _store()
    assert _assign_tier(store, {"seed"}, "seed") == 0


def test_tier_assignment_direct_call_neighbor_is_tier_1():
    store = _store()
    assert _assign_tier(store, {"seed"}, "callee") == 1


def test_tier_assignment_class_node_is_tier_2():
    store = _store()
    assert _assign_tier(store, {"seed"}, "cls_base") == 2


def test_tier_assignment_unrelated_is_tier_3():
    store = _store()
    assert _assign_tier(store, {"seed"}, "distant") == 3


def test_compile_stops_at_token_budget():
    store = _store()
    bundle = compile(store, root=None, seed_ids=["seed"], ranked_ids=["callee", "cls_base", "distant"], max_tokens=5)
    assert isinstance(bundle, ContextBundle)
    assert bundle.used_tokens <= 5
    # seed always included even under a tiny budget (it's added first, before the check
    # against later candidates), later candidates degrade to stubs or get dropped
    assert bundle.items[0].qid == "seed"


def test_compile_respects_generous_budget_includes_all():
    store = _store()
    bundle = compile(store, root=None, seed_ids=["seed"], ranked_ids=["callee", "cls_base", "distant"], max_tokens=5000)
    ids = {it.qid for it in bundle.items}
    assert {"seed", "callee", "cls_base", "distant"} <= ids


def test_count_tokens_nonzero_for_nonempty_text():
    assert count_tokens("def f(): pass") > 0


def test_build_context_no_keys_returns_placeholder():
    store = MemoryStore()
    bundle = build_context(store, root=None)
    assert "No files or symbols" in bundle.rendered_prompt
    assert bundle.seeds == []


def test_retrieve_without_reranker_matches_default_fuse_rrf_behavior():
    """learned_reranker=None (the default everywhere it's threaded through) must
    behave identically to before it existed — settings.enable_learned_rerank defaults
    to False specifically so this is the behavior every existing caller still gets."""
    store = _store()
    ranked = retrieve(store, ["seed"], semantic_hits=[("callee", 0.9), ("distant", 0.1)])
    assert "callee" in ranked
    assert "distant" in ranked


def test_retrieve_calls_learned_reranker_with_full_candidate_set():
    """Contract test for the opt-in wiring (context/pipeline.py::retrieve +
    saas/app.py's/mcp/server.py's settings.enable_learned_rerank path): when given a
    reranker, `retrieve` must build features over the *union* of PPR + semantic
    candidates and hand them to it — it blends the reranker's ranking into fuse_rrf as
    a third list (eval/results/reranker.md's "blend" variant) rather than replacing
    RRF outright, so asserting an exact final order here would just be re-testing RRF
    arithmetic; what's actually new and worth covering is that the reranker gets
    invoked at all, with the right inputs. A stub stands in for the real
    `queries.learned_rerank.LearnedReranker` — its ranking *quality* is what
    eval/results/reranker.md measures, not this plumbing test."""
    calls = []

    class SpyReranker:
        def rank(self, feats):
            calls.append(set(feats.keys()))
            return list(feats.keys())

    store = _store()
    ranked = retrieve(
        store,
        ["seed"],
        semantic_hits=[("callee", 0.9), ("distant", 0.1)],
        bfs_nodes=[],
        learned_reranker=SpyReranker(),
    )
    assert len(calls) == 1
    assert calls[0] >= {"callee", "distant"}
    assert set(ranked) >= {"callee", "distant"}
