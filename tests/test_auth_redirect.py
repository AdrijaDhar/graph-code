"""Regression tests for a real bug caught live: both OAuth redirect targets were
hardcoded to http://localhost:3000/app, which only ever worked by coincidence in
local dev (the frontend genuinely was on :3000 there). Deploying for real sent every
signed-in user's browser back to their own localhost instead of the real site.
"""

from __future__ import annotations

from urllib.parse import unquote

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
    client.cookies.set("oauth_state", "matching-state")
    resp = client.get(
        "/v1/auth/github/callback", params={"code": "fake", "state": "matching-state"}, follow_redirects=False
    )
    assert resp.status_code in (302, 307)
    # Carries a one-time signed token in the redirect URL, not just the gc_session
    # cookie — a cookie set only during this callback's redirect "bounce" (GitHub ->
    # our API domain -> immediately on to the frontend domain) is exactly what modern
    # browsers' bounce-tracking mitigations silently discard on a deployment where the
    # frontend and API are on different domains (confirmed live). The frontend picks
    # this up once and sends it back as a Bearer header from then on.
    location = resp.headers["location"]
    assert location.startswith("https://example-frontend.test/app?token=")
    client.cookies.clear()


def test_session_token_from_oauth_redirect_authenticates_via_bearer_header(monkeypatch):
    """The actual fix for a real production bug: a `gc_session` cookie set only
    during the OAuth callback's redirect "bounce" (GitHub -> our API domain ->
    immediately on to the frontend domain) was confirmed live to never reach the
    browser's cookie store at all, in Safari, Chrome, and Chrome Incognito alike, on
    a deployment where the frontend and API are on separate domains — modern
    browsers' bounce-tracking mitigations discard it. The callback now also hands the
    same signed token to the frontend via the redirect URL, for it to send back as a
    Bearer header instead — this checks that a request carrying only that header (no
    cookie at all) authenticates exactly like the cookie used to."""
    monkeypatch.setattr(
        app_module, "exchange_github_code", lambda code: {"id": 456, "login": "hubot", "name": "Hu Bot"}
    )
    client.cookies.set("oauth_state", "matching-state-2")
    resp = client.get(
        "/v1/auth/github/callback", params={"code": "fake", "state": "matching-state-2"}, follow_redirects=False
    )
    # The token is URL-encoded in the raw Location header (real browsers decode this
    # automatically via URLSearchParams, same as lib/api.ts's captureTokenFromUrl) —
    # decode it here too, or the signature simply won't match.
    token = unquote(resp.headers["location"].split("token=", 1)[1])
    client.cookies.clear()  # no cookie at all from here on — Bearer must carry the whole session

    me = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["user"]["login"] == "hubot"


def test_oauth_callback_rejects_mismatched_state(monkeypatch):
    """Regression test for a real login-CSRF gap: state used to be accepted (or even
    entirely absent) without being checked against anything at all."""
    monkeypatch.setattr(
        app_module, "exchange_github_code", lambda code: {"id": 123, "login": "octocat", "name": "The Octocat"}
    )
    client.cookies.set("oauth_state", "real-state")
    resp = client.get(
        "/v1/auth/github/callback", params={"code": "fake", "state": "attacker-supplied-state"}, follow_redirects=False
    )
    assert resp.status_code == 400
    client.cookies.clear()


def test_oauth_callback_rejects_missing_state_cookie(monkeypatch):
    monkeypatch.setattr(
        app_module, "exchange_github_code", lambda code: {"id": 123, "login": "octocat", "name": "The Octocat"}
    )
    resp = client.get("/v1/auth/github/callback", params={"code": "fake", "state": "anything"}, follow_redirects=False)
    assert resp.status_code == 400


def test_unauthenticated_request_rejected_once_oauth_is_configured(monkeypatch):
    """Regression test for a real bug caught live: once GitHub OAuth is configured (any
    real deployment), an unauthenticated request used to silently fall back to a
    single SHARED demo account instead of being rejected — meaning two different
    strangers who both skip signing in on a live site would land in the identical org
    and see each other's indexed repos."""
    monkeypatch.setattr(settings, "github_client_id", "configured")
    resp = client.get("/v1/me")
    assert resp.status_code == 401


def test_unauthenticated_falls_back_to_demo_only_when_oauth_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "github_client_id", "")
    resp = client.get("/v1/me")
    assert resp.status_code == 200
    assert resp.json()["user"]["login"] == "demo"


def test_view_blast_requires_authentication(monkeypatch):
    """Regression test: /view/blast used to have no auth dependency at all, and
    queried the graph with no org_id — reachable by anyone, and scoped to nothing."""
    monkeypatch.setattr(settings, "github_client_id", "configured")
    resp = client.get("/view/blast", params={"symbol": "parse_config"})
    assert resp.status_code == 401


def test_view_blast_escapes_symbol_in_response(monkeypatch):
    """Regression test for reflected XSS: `symbol` used to be interpolated into the
    HTML response with no escaping at all."""
    monkeypatch.setattr(settings, "github_client_id", "")  # demo fallback, so this is reachable
    resp = client.get("/view/blast", params={"symbol": "<script>alert(1)</script>"})
    assert resp.status_code == 200
    assert "<script>alert(1)</script>" not in resp.text
    assert "&lt;script&gt;" in resp.text


def test_session_cookie_uses_samesite_none_and_secure_over_https():
    """Regression test: the frontend and backend live on different subdomains in
    production and the frontend calls the API with credentials:"include" — a plain
    SameSite=Lax cookie (the default) is silently dropped on that kind of cross-site
    fetch, only surviving top-level navigations. Without this, real sign-in would
    appear to work (the OAuth redirect itself is a top-level nav) right up until the
    first subsequent API call, which would come back 401 with no session."""
    kwargs = app_module.session_cookie_kwargs(https_deployment=True)
    assert kwargs["secure"] is True
    assert kwargs["samesite"] == "none"


def test_session_cookie_uses_samesite_lax_over_plain_http():
    """SameSite=None without Secure is rejected outright by browsers, and Secure
    cookies are never sent back over plain http://localhost — so the production fix
    above must not be applied to local dev, or it breaks local sign-in instead."""
    kwargs = app_module.session_cookie_kwargs(https_deployment=False)
    assert kwargs["secure"] is False
    assert kwargs["samesite"] == "lax"


def test_logout_clears_session_cookie_and_redirects():
    """Regression test: there was previously no sign-out path anywhere in the app at
    all — confirmed live, a real user with a real session had no way to end it short
    of manually clearing cookies in devtools."""
    monkeypatch_settings = settings.frontend_url
    resp = client.get("/v1/auth/logout", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == f"{monkeypatch_settings}/"
    set_cookie = resp.headers.get("set-cookie", "")
    assert "gc_session=" in set_cookie
    # A cleared cookie is set with an empty value and an expiry in the past —
    # confirming this actually clears it, not just redirects without doing anything.
    assert 'gc_session=""' in set_cookie or "gc_session=;" in set_cookie
