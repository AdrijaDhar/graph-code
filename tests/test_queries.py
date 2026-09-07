from pathlib import Path

from graphcode.indexer import IndexService
from graphcode.queries.call_chain import call_chain
from graphcode.queries.paths import blast_radius, graph_overview, shortest_path, suggest_starting_points

ROOT = Path(__file__).parent / "fixtures" / "mini_repo"


def test_call_chain_and_path(tmp_path):
    svc = IndexService(rocks_path=tmp_path / "rocks")
    svc.index_repo(ROOT, parallel=False)
    chain = call_chain(svc.memory, "handle_request")
    assert "paths" in chain
    sp = shortest_path(svc.memory, "ApiController", "parse_config")
    assert isinstance(sp.get("path"), list)


def test_queries_scope_by_org_id_no_cross_tenant_leak(tmp_path):
    """Regression test for a real cross-tenant leak: IndexService._hydrate() warm-loads
    every org's persisted snapshots into one shared MemoryStore (by design, so a
    multi-org SaaS process can serve concurrent orgs), but find()/blast_radius()/
    shortest_path()/call_chain() had no org_id filtering at all — an org_id="org_b"
    caller could resolve and traverse into org_a's private repo just by naming a
    symbol that happens to exist there too, since resolution is name-based, not
    id-based. Simulates that exact scenario: two different repos indexed into the
    same store under different org_ids, one of them (org_b) reusing a symbol name
    ("parse_config") that only actually exists in org_a's repo."""
    svc = IndexService(rocks_path=tmp_path / "rocks")
    svc.index_repo(ROOT, org_id="org_a", repo_id="a", parallel=False)

    org_b_root = tmp_path / "org_b_repo"
    (org_b_root / "src").mkdir(parents=True)
    (org_b_root / "src" / "only_in_b.py").write_text("def only_in_b():\n    return 1\n")
    svc.index_repo(org_b_root, org_id="org_b", repo_id="b", parallel=False)

    # org_b has no parse_config of its own — scoped lookup must not fall through to
    # org_a's, even though org_a's is sitting right there in the same store.
    assert blast_radius(svc.memory, "parse_config", org_id="org_b")["nodes"] == []
    assert shortest_path(svc.memory, "parse_config", "only_in_b", org_id="org_b")["path"] == []
    assert call_chain(svc.memory, "parse_config", org_id="org_b")["paths"] == []

    # org_a's own query for the same symbol still resolves normally — scoping isn't
    # just blanket-blocking everything.
    assert blast_radius(svc.memory, "parse_config", org_id="org_a").get("origin")

    # unscoped (org_id=None, the default) preserves pre-fix behavior for single-tenant
    # callers (the standalone CLI/MCP server) that never pass org_id at all.
    assert blast_radius(svc.memory, "parse_config").get("origin")


def test_blast_radius_nodes_carry_from_field_for_edge_reconstruction(tmp_path):
    """The web UI's dependency-graph visualization needs real (source, target) edges,
    not just each node's hop distance — 'from' records which already-seen node this
    one was discovered from during the BFS."""
    svc = IndexService(rocks_path=tmp_path / "rocks")
    svc.index_repo(ROOT, parallel=False)
    br = blast_radius(svc.memory, "handle_request", direction="upstream", max_hops=3)
    nodes = br["nodes"]
    assert nodes[0].get("from") is None  # origin has no discoverer
    non_origin = nodes[1:]
    assert non_origin, "expected at least one related node in the fixture"
    for n in non_origin:
        assert "from" in n
        # the 'from' id must point at some other node actually present in the result
        assert n["from"] in {x["id"] for x in nodes}


def test_graph_overview_returns_module_level_nodes_and_edges(tmp_path):
    svc = IndexService(rocks_path=tmp_path / "rocks")
    svc.index_repo(ROOT, parallel=False)
    result = graph_overview(svc.memory)
    assert result["nodes"], "expected at least one module in the fixture"
    assert all(n["label"] == "Module" for n in result["nodes"])
    # every edge must reference nodes actually present in the result, not dangling ids
    node_ids = {n["id"] for n in result["nodes"]}
    for e in result["edges"]:
        assert e["source"] in node_ids
        assert e["target"] in node_ids
    assert result["truncated"] is False


def test_graph_overview_size_reflects_contained_symbol_count(tmp_path):
    """`size` is used for node sizing in the frontend visualization — a module with
    more functions/classes should report a larger size than an empty one."""
    svc = IndexService(rocks_path=tmp_path / "rocks")
    svc.index_repo(ROOT, parallel=False)
    result = graph_overview(svc.memory)
    by_path = {n["path"]: n["size"] for n in result["nodes"] if "path" in n}
    utils = by_path.get("src/utils.py")
    assert utils is not None and utils > 0


def test_graph_overview_truncates_and_flags_when_over_max_nodes(tmp_path):
    svc = IndexService(rocks_path=tmp_path / "rocks")
    svc.index_repo(ROOT, parallel=False)
    result = graph_overview(svc.memory, max_nodes=1)
    assert len(result["nodes"]) == 1
    assert result["truncated"] is True


def test_graph_overview_scoped_by_org_id(tmp_path):
    from graphcode.loader.memory import MemoryStore
    from graphcode.schema import GraphBatch, GraphNode

    store = MemoryStore()
    store.load_batch(
        GraphBatch(nodes=[GraphNode(id="m1", label="Module", props={"path": "a.py"})]), org_id="org1"
    )
    store.load_batch(
        GraphBatch(nodes=[GraphNode(id="m2", label="Module", props={"path": "b.py"})]), org_id="org2"
    )
    result = graph_overview(store, org_id="org1")
    assert {n["id"] for n in result["nodes"]} == {"m1"}


def test_suggest_starting_points_ranks_by_real_dependent_count(tmp_path):
    svc = IndexService(rocks_path=tmp_path / "rocks")
    svc.index_repo(ROOT, parallel=False)
    result = suggest_starting_points(svc.memory)
    assert result["suggestions"], "expected at least one suggestion in the fixture"
    # results must be sorted descending by dependent_count, and every one must be a
    # real function/class (not a Module or Variable — this ranks "what's relied on
    # behaviorally", not files)
    counts = [s["dependent_count"] for s in result["suggestions"]]
    assert counts == sorted(counts, reverse=True)
    assert all(s["label"] in ("Function", "Class") for s in result["suggestions"])
    assert all(s["dependent_count"] >= 1 for s in result["suggestions"])


def test_suggest_starting_points_counts_distinct_callers_not_call_sites():
    from graphcode.loader.memory import MemoryStore
    from graphcode.schema import GraphBatch, GraphEdge, GraphNode

    store = MemoryStore()
    store.load_batch(
        GraphBatch(
            nodes=[
                GraphNode(id="target", label="Function", props={"name": "target"}),
                GraphNode(id="caller", label="Function", props={"name": "caller"}),
            ],
            # two CALLS edges from the *same* caller must count as one dependent, not two
            edges=[GraphEdge(type="CALLS", from_id="caller", to_id="target")] * 2,
        )
    )
    result = suggest_starting_points(store)
    hit = next(s for s in result["suggestions"] if s["id"] == "target")
    assert hit["dependent_count"] == 1


def test_suggest_starting_points_scoped_by_org_id():
    from graphcode.loader.memory import MemoryStore
    from graphcode.schema import GraphBatch, GraphEdge, GraphNode

    store = MemoryStore()
    store.load_batch(
        GraphBatch(
            nodes=[
                GraphNode(id="t1", label="Function", props={"name": "t1"}),
                GraphNode(id="c1", label="Function", props={"name": "c1"}),
            ],
            edges=[GraphEdge(type="CALLS", from_id="c1", to_id="t1")],
        ),
        org_id="org1",
    )
    store.load_batch(GraphBatch(nodes=[GraphNode(id="t2", label="Function", props={"name": "t2"})]), org_id="org2")
    result = suggest_starting_points(store, org_id="org2")
    assert result["suggestions"] == []
