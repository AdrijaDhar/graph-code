from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from graphcode.indexer import get_index_service
from graphcode.saas.app import app

ROOT = Path(__file__).parent / "fixtures" / "mini_repo"


def _index_as_current_org(client: TestClient) -> None:
    """Indexes ROOT under the *actual* org_id the demo-fallback session resolves to
    (a real numeric org id from the database), not the indexer's own default
    ("local") — these endpoints correctly org-scope every query, so a test indexing
    under a different org_id than the one it queries as would see nothing, for the
    same reason a different real tenant would see nothing (this is the fix, not a
    bug to work around)."""
    org_id = str(client.get("/v1/me").json()["org"]["id"])
    get_index_service().index_repo(ROOT, org_id=org_id, parallel=False)


def test_graph_overview_endpoint_returns_module_graph():
    client = TestClient(app)
    _index_as_current_org(client)
    resp = client.get("/v1/graph/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["nodes"]
    assert all(n["label"] == "Module" for n in body["nodes"])
    node_ids = {n["id"] for n in body["nodes"]}
    for e in body["edges"]:
        assert e["source"] in node_ids
        assert e["target"] in node_ids


def test_symbol_search_endpoint_returns_matches():
    client = TestClient(app)
    _index_as_current_org(client)
    resp = client.get("/v1/symbols/search", params={"q": "parse_config"})
    assert resp.status_code == 200
    body = resp.json()
    assert any("parse_config" in (r.get("qualified_name") or "") for r in body["results"])


def test_graph_suggestions_endpoint_returns_ranked_starting_points():
    client = TestClient(app)
    _index_as_current_org(client)
    resp = client.get("/v1/graph/suggestions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["suggestions"]
    assert all(s["label"] in ("Function", "Class") for s in body["suggestions"])
