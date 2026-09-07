from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from graphcode.indexer import get_index_service
from graphcode.saas.app import app

ROOT = Path(__file__).parent / "fixtures" / "mini_repo"


def test_files_source_returns_real_slice():
    get_index_service().index_repo(ROOT, parallel=False)
    client = TestClient(app)
    resp = client.get("/v1/files/source", params={"path": "src/utils.py", "start": 1, "end": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["path"] == "src/utils.py"
    assert "def parse_config" in body["text"]


def test_files_source_rejects_path_traversal():
    get_index_service().index_repo(ROOT, parallel=False)
    client = TestClient(app)
    resp = client.get("/v1/files/source", params={"path": "../../../../etc/passwd"})
    assert resp.status_code == 400


def test_files_source_404s_for_missing_file():
    get_index_service().index_repo(ROOT, parallel=False)
    client = TestClient(app)
    resp = client.get("/v1/files/source", params={"path": "no/such/file.py"})
    assert resp.status_code == 404
