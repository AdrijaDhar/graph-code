from __future__ import annotations

import hashlib
import hmac
import secrets
from urllib.parse import urlencode

import httpx

from graphcode.config import settings
from graphcode.saas.models import ApiKey, Membership, Org, User, get_session


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create_api_key(org_id: int) -> str:
    raw = "gc_live_" + secrets.token_urlsafe(24)
    s = get_session()
    try:
        s.add(ApiKey(org_id=org_id, prefix=raw[:12], hashed=_hash_key(raw)))
        s.commit()
    finally:
        s.close()
    return raw


def org_for_api_key(raw: str) -> Org | None:
    s = get_session()
    try:
        hashed = _hash_key(raw)
        key = s.query(ApiKey).filter_by(hashed=hashed, revoked=0).first()
        if not key:
            return None
        return s.get(Org, key.org_id)
    finally:
        s.close()


def upsert_github_user(github_id: str, login: str, name: str) -> tuple[User, Org]:
    s = get_session()
    try:
        user = s.query(User).filter_by(github_id=str(github_id)).first()
        if not user:
            user = User(github_id=str(github_id), login=login, name=name or login)
            s.add(user)
            s.flush()
            org = Org(name=f"{login}-org")
            s.add(org)
            s.flush()
            s.add(Membership(user_id=user.id, org_id=org.id, role="owner"))
            s.commit()
            s.refresh(user)
            s.refresh(org)
            return user, org
        mem = s.query(Membership).filter_by(user_id=user.id).first()
        org = s.get(Org, mem.org_id) if mem else None
        if org is None:
            org = Org(name=f"{login}-org")
            s.add(org)
            s.flush()
            s.add(Membership(user_id=user.id, org_id=org.id, role="owner"))
            s.commit()
        return user, org
    finally:
        s.close()


def github_login_url(state: str) -> str:
    qs = urlencode(
        {
            "client_id": settings.github_client_id,
            "redirect_uri": f"{settings.public_base_url}/v1/auth/github/callback",
            "scope": "read:user user:email",
            "state": state,
        }
    )
    return f"https://github.com/login/oauth/authorize?{qs}"


def exchange_github_code(code: str) -> dict | None:
    if not settings.github_client_id:
        return None
    r = httpx.post(
        "https://github.com/login/oauth/access_token",
        json={
            "client_id": settings.github_client_id,
            "client_secret": settings.github_client_secret,
            "code": code,
        },
        headers={"Accept": "application/json"},
        timeout=20,
    )
    data = r.json()
    token = data.get("access_token")
    if not token:
        return None
    u = httpx.get(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=20,
    )
    return u.json()


def sign_session(payload: str) -> str:
    sig = hmac.new(settings.session_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_session(cookie: str) -> str | None:
    if "." not in cookie:
        return None
    payload, sig = cookie.rsplit(".", 1)
    expect = hmac.new(settings.session_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, sig):
        return None
    return payload
