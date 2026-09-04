from __future__ import annotations

import httpx
import pytest

from graphcode.config import settings
from graphcode.saas.auth import (
    exchange_github_code,
    github_login_url,
    sign_session,
    verify_session,
)


def test_sign_and_verify_session_roundtrip():
    cookie = sign_session("user:42")
    assert verify_session(cookie) == "user:42"


def test_verify_session_rejects_tampered_cookie():
    cookie = sign_session("user:42")
    tampered = cookie[:-1] + ("0" if cookie[-1] != "0" else "1")
    assert verify_session(tampered) is None


def test_verify_session_rejects_missing_signature():
    assert verify_session("no-dot-here") is None


def test_github_login_url_contains_client_id_and_state(monkeypatch):
    monkeypatch.setattr(settings, "github_client_id", "test-client-id")
    url = github_login_url("state123")
    assert "client_id=test-client-id" in url
    assert "state=state123" in url
    assert url.startswith("https://github.com/login/oauth/authorize?")


def test_exchange_github_code_without_client_id_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "github_client_id", "")
    assert exchange_github_code("some-code") is None


def test_exchange_github_code_does_real_token_and_user_calls(monkeypatch):
    """Verify the OAuth exchange hits the real GitHub endpoints (mocked here),
    not a demo/fake path."""
    monkeypatch.setattr(settings, "github_client_id", "cid")
    monkeypatch.setattr(settings, "github_client_secret", "csecret")

    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append(("POST", url, json))
        return httpx.Response(200, json={"access_token": "tok_abc"}, request=httpx.Request("POST", url))

    def fake_get(url, headers=None, timeout=None):
        calls.append(("GET", url, headers))
        return httpx.Response(200, json={"id": 1, "login": "octocat"}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)

    result = exchange_github_code("some-code")
    assert result == {"id": 1, "login": "octocat"}
    assert calls[0][1] == "https://github.com/login/oauth/access_token"
    assert calls[0][2]["code"] == "some-code"
    assert calls[1][1] == "https://api.github.com/user"
    assert calls[1][2]["Authorization"] == "Bearer tok_abc"
