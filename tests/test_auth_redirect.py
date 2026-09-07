"""Regression tests for a real bug caught live: both OAuth redirect targets were
hardcoded to http://localhost:3000/app, which only ever worked by coincidence in
local dev (the frontend genuinely was on :3000 there). Deploying for real sent every
signed-in user's browser back to their own localhost instead of the real site.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from graphcode.config import settings
from graphcode.saas import app as app_module

client = TestClient(app_module.app)


def test_demo_login_redirects_to_configured_frontend_url(monkeypatch):
    monkeypatch.setattr(settings, "frontend_url", "https://example-frontend.test")
    monkeypatch.setattr(settings, "github_client_id", "")  # no OAuth app configured -> demo fallback
    resp = client.get("/v1/auth/github", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "https://example-frontend.test/app"


def test_oauth_callback_redirects_to_configured_frontend_url(monkeypatch):
    monkeypatch.setattr(settings, "frontend_url", "https://example-frontend.test")
    monkeypatch.setattr(
        app_module, "exchange_github_code", lambda code: {"id": 123, "login": "octocat", "name": "The Octocat"}
    )
    resp = client.get("/v1/auth/github/callback", params={"code": "fake"}, follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "https://example-frontend.test/app"
