from __future__ import annotations

import html
import secrets
import time
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import func

from graphcode.config import settings
from graphcode.context.compiler import compile_context, slice_source
from graphcode.context.pipeline import build_context
from graphcode.indexer import get_index_service
from graphcode.queries.call_chain import call_chain
from graphcode.queries.copilot import ask as copilot_ask
from graphcode.queries.hybrid import semantic_search
from graphcode.queries.paths import blast_radius, graph_overview, shortest_path, suggest_starting_points
from graphcode.queries.test_impact import find_affected_tests
from graphcode.saas.admin import admin_overview, is_admin
from graphcode.saas.auth import (
    create_api_key,
    exchange_github_code,
    github_login_url,
    sign_session,
    upsert_github_user,
    verify_session,
)
from graphcode.saas.billing import create_checkout_session, handle_webhook_event, parse_webhook_event
from graphcode.saas.models import Membership, Org, RepoRecord, User, get_session, init_db
from graphcode.saas.usage import check_quota, record_usage, remaining
from graphcode.watcher.daemon import get_watch

app = FastAPI(title="Graph-Code Copilot", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def session_cookie_kwargs(https_deployment: bool) -> dict:
    """The frontend and backend are deployed on *different* subdomains in production
    (e.g. graph-code-web.onrender.com vs graph-code-api.onrender.com) and the frontend
    calls the API with `credentials: "include"` — a plain SameSite=Lax cookie (the
    default) is not sent on that kind of cross-site fetch, only on top-level page
    navigations. SameSite=None is required for it to actually arrive, and browsers
    reject SameSite=None cookies outright unless Secure is also set. Only enable this
    when actually serving over HTTPS — SameSite=None without HTTPS breaks local dev
    instead of fixing anything, since a Secure cookie is never sent back over plain
    http://localhost."""
    return {
        "httponly": True,
        "secure": https_deployment,
        "samesite": "none" if https_deployment else "lax",
    }


_SESSION_COOKIE_KWARGS = session_cookie_kwargs(settings.public_base_url.startswith("https://"))


@app.on_event("startup")
def _startup():
    Path("data").mkdir(exist_ok=True)
    init_db()
    get_index_service()


class RepoIn(BaseModel):
    name: str
    github_url: str = ""
    local_path: str = ""


class QueryIn(BaseModel):
    symbol: str | None = None
    from_symbol: str | None = None
    to_symbol: str | None = None
    direction: str = "upstream"
    prompt: str = ""
    files: list[str] | None = None
    symbols: list[str] | None = None
    max_tokens: int = 8000
    query: str | None = None
    k: int = 8


def _user_from_request(request: Request, authorization: str | None) -> tuple[User | None, Org | None]:
    s = get_session()
    try:
        bearer = None
        if authorization and authorization.lower().startswith("bearer "):
            from graphcode.saas.auth import org_for_api_key

            bearer = authorization.split(" ", 1)[1]
            org = org_for_api_key(bearer)
            if org:
                mem = s.query(Membership).filter_by(org_id=org.id).first()
                user = s.get(User, mem.user_id) if mem else None
                return user, org
        # Session identity, checked as a signed token from either a cookie or a
        # Bearer header — the Bearer path exists because a `gc_session` cookie set
        # only during the OAuth callback's redirect "bounce" (GitHub -> our API
        # domain -> immediately on to the frontend domain) gets silently discarded by
        # modern browsers' bounce-tracking mitigations before it's ever stored, on a
        # deployment where the frontend and API are on different domains (confirmed
        # live: gc_session never appeared in the cookie store at all, in Safari,
        # Chrome, and Chrome Incognito alike — not a SameSite/Secure misconfiguration,
        # since the header itself was verified correct). auth_callback below hands the
        # same signed token to the frontend via the redirect URL instead, for the
        # frontend to carry itself as an Authorization header from then on, which no
        # cookie policy touches. The cookie path is kept too — it's what actually
        # works for same-site/local-dev deployments, so this isn't a regression there.
        session_token = bearer or request.cookies.get("gc_session")
        if session_token:
            payload = verify_session(session_token)
            if payload and payload.startswith("u:"):
                uid = int(payload.split(":")[1])
                user = s.get(User, uid)
                if user:
                    mem = s.query(Membership).filter_by(user_id=user.id).first()
                    org = s.get(Org, mem.org_id) if mem else None
                    return user, org
        # Local demo user — but ONLY when OAuth genuinely isn't configured (matches
        # auth_github()'s own local-dev fallback). Confirmed live as a real bug: with
        # OAuth configured (any real deployment), this used to fall back to the SAME
        # shared demo account for *any* unauthenticated request regardless — meaning
        # two different strangers who both skip signing in on a live deployment would
        # silently land in the identical org and see each other's indexed repos.
        if not settings.github_client_id:
            user, org = upsert_github_user("0", "demo", "Demo User")
            return user, org
        return None, None
    finally:
        s.close()


def require_user(request: Request, authorization: str | None = Header(default=None)):
    user, org = _user_from_request(request, authorization)
    if not user or not org:
        raise HTTPException(401, "unauthorized")
    return user, org


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def home():
    svc = get_index_service()
    indexed = svc.last_index or {}
    counts = indexed.get("counts") or {}
    s = get_session()
    try:
        from graphcode.saas.models import UsageEvent

        users = s.query(User).count()
        orgs = s.query(Org).count()
        repos = s.query(RepoRecord).count()
        queries = s.query(UsageEvent).filter(UsageEvent.kind.like("query%")).count()
    finally:
        s.close()
    files = indexed.get("files") or 0
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Graph-Code</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; max-width: 720px; margin: 40px auto; padding: 0 20px;
           background:#0b1020; color:#e8eefc; line-height:1.5; }}
    a {{ color:#8ecbff; }}
    .card {{ background:#151b30; border:1px solid #2a3558; border-radius:12px; padding:20px; margin:16px 0; }}
    input, button {{ font-size:16px; padding:8px 12px; border-radius:8px; border:1px solid #3a4a72; }}
    button {{ background:#2d6cdf; color:white; cursor:pointer; }}
    pre {{ white-space:pre-wrap; font-size:13px; background:#0a0e1a; padding:12px; border-radius:8px; overflow:auto; }}
    .muted {{ color:#9aa6c4; }}
  </style>
</head>
<body>
  <h1>Graph-Code</h1>
  <p>This is the product. The other page (<code>/docs</code>) is a raw developer list of APIs — skip it for now.</p>
  <p>Idea in one sentence: if you change a function, this graph shows <b>what else in the repo might break</b>, even files you do not have open.</p>

  <div class="card">
    <h2>What is indexed right now</h2>
    <p>Files: <b>{files}</b> &nbsp; Functions: <b>{counts.get("Function", 0)}</b> &nbsp; Classes: <b>{counts.get("Class", 0)}</b></p>
    <p class="muted">Users {users} · Orgs {orgs} · Repos {repos} · Queries {queries}</p>
  </div>

  <div class="card">
    <h2>Try the main question</h2>
    <p class="muted">Type a function name from the sample repo, e.g. <code>parse_config</code></p>
    <form action="/view/blast" method="get">
      <input name="symbol" value="parse_config" />
      <button type="submit">What depends on this?</button>
    </form>
  </div>

  <p class="muted">Keep this tab. You do not need Swagger unless you are wiring an MCP client (see <code>graphcode chat</code>).</p>
</body>
</html>"""


@app.get("/view/blast", response_class=HTMLResponse)
def view_blast(symbol: str = "parse_config", ctx=Depends(require_user)):
    # Was fully unauthenticated and queried the shared MemoryStore with no org_id at
    # all — on a real deployment with more than one org's data hydrated, anyone (no
    # login needed) could pull another org's blast-radius data just by guessing a
    # symbol name. Also had a reflected-XSS gap: `symbol` and the graph's own
    # name/path/label strings went straight into the HTML response unescaped.
    _, org = ctx
    data = blast_radius(get_index_service().memory, symbol, direction="upstream", org_id=str(org.id))
    origin = data.get("origin") or {}
    rows = []
    for n in data.get("nodes") or []:
        name = html.escape(str(n.get("qualified_name") or n.get("path") or n.get("name") or ""))
        via = html.escape(str(n.get("via") or "origin"))
        label = html.escape(str(n.get("label") or ""))
        rows.append(f"<li><b>{label}</b> — {name} <span class='muted'>({via})</span></li>")
    err = data.get("error")
    body = f"<p><b>Error:</b> {html.escape(str(err))}</p>" if err else f"<ul>{''.join(rows)}</ul>"
    title = html.escape(str(origin.get("qualified_name") or symbol))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/><title>Blast radius</title>
<style>
  body {{ font-family: ui-sans-serif, system-ui, sans-serif; max-width: 720px; margin: 40px auto; padding: 0 20px;
         background:#0b1020; color:#e8eefc; line-height:1.5; }}
  a {{ color:#8ecbff; }} li {{ margin: 8px 0; }} .muted {{ color:#9aa6c4; }}
</style></head>
<body>
  <p><a href="/">← Back</a></p>
  <h1>What is connected to {title}?</h1>
  <p class="muted">These are files/functions in the graph that sit near that symbol (imports, containment, calls).</p>
  {body}
</body></html>"""


@app.get("/v1/auth/github")
def auth_github():
    if not settings.github_client_id:
        user, org = upsert_github_user("0", "demo", "Demo User")
        resp = RedirectResponse(url=f"{settings.frontend_url}/app")
        resp.set_cookie("gc_session", sign_session(f"u:{user.id}"), **_SESSION_COOKIE_KWARGS)
        return resp
    # state is stored in a short-lived cookie and re-checked in the callback below —
    # without this, a login-CSRF is possible: an attacker starts their own OAuth flow,
    # gets a valid `code` for their own account, and sends a victim a link straight to
    # the callback with that code. The callback would exchange it, authenticate as the
    # attacker's identity, and set the *victim's* browser session to it — tricking the
    # victim into unknowingly using the attacker's account (and everything they do
    # there being visible to the attacker afterward). The random, per-attempt state
    # value breaks this: the attacker can't predict what state the victim's browser
    # cookie will hold, so a code+state pair generated for the attacker's own flow
    # won't match.
    state = secrets.token_urlsafe(16)
    resp = RedirectResponse(github_login_url(state))
    resp.set_cookie("oauth_state", state, httponly=True, max_age=600, samesite="lax")
    return resp


@app.get("/v1/auth/github/callback")
def auth_callback(request: Request, code: str = "", state: str = ""):
    expected_state = request.cookies.get("oauth_state")
    if not expected_state or not secrets.compare_digest(state, expected_state):
        raise HTTPException(400, "invalid oauth state")
    info = exchange_github_code(code)
    if not info:
        raise HTTPException(400, "oauth failed")
    user, org = upsert_github_user(str(info.get("id")), info.get("login") or "user", info.get("name") or "")
    token = sign_session(f"u:{user.id}")
    # The token is also handed to the frontend via the redirect URL, not just the
    # cookie below — a cookie set only during this callback's redirect "bounce"
    # (GitHub -> here -> immediately on to the frontend's own domain) is exactly the
    # pattern modern browsers' bounce-tracking mitigations silently discard before the
    # frontend ever gets a chance to use it, on a deployment where the frontend and
    # API are on different domains (confirmed live, see _user_from_request). The
    # frontend picks this up once, stores it, and sends it as a Bearer header from
    # then on — see apps/web/app/lib/api.ts.
    resp = RedirectResponse(url=f"{settings.frontend_url}/app?token={quote(token)}")
    resp.set_cookie("gc_session", token, **_SESSION_COOKIE_KWARGS)
    resp.delete_cookie("oauth_state")
    return resp


@app.get("/v1/auth/logout")
def auth_logout():
    """There was no sign-out path anywhere in the app — confirmed live: a user with a
    real session had no way to end it short of manually clearing cookies, and the
    logo link goes to `/`, a public landing page that isn't auth-aware and shows a
    sign-in prompt regardless of session state, easy to mistake for "you got logged
    out" when nothing actually changed."""
    resp = RedirectResponse(url=f"{settings.frontend_url}/")
    resp.delete_cookie("gc_session")
    return resp


@app.get(" /v1/me".replace(" ", ""))
def me(ctx=Depends(require_user)):
    user, org = ctx
    return {
        "user": {"id": user.id, "login": user.login, "github_id": user.github_id},
        "org": {"id": org.id, "name": org.name, "plan": org.plan},
        "usage": remaining(org.id, org.plan),
        # True whenever this deployment has no GitHub OAuth configured — every request
        # resolves to the same shared demo account regardless of cookies (see
        # _user_from_request's demo fallback), so there is no real session for "Sign
        # out" to end: it clears a cookie that was never required, then the very next
        # request falls right back into the same demo account. The frontend uses this
        # to show "Demo mode" instead of a Sign out link that would look broken —
        # confirmed live as the actual cause of a "sign out does nothing" report.
        "demo": not bool(settings.github_client_id),
    }


@app.get("/v1/org")
def org_info(ctx=Depends(require_user)):
    user, org = ctx
    s = get_session()
    try:
        members = s.query(Membership).filter_by(org_id=org.id).all()
        people = []
        for m in members:
            u = s.get(User, m.user_id)
            people.append({"login": u.login if u else "?", "role": m.role})
        return {"org": org.name, "plan": org.plan, "members": people}
    finally:
        s.close()


@app.post("/v1/org/invite")
def invite(login: str, ctx=Depends(require_user)):
    _, org = ctx
    guest, _ = upsert_github_user(f"invite-{login}", login, login)
    s = get_session()
    try:
        existing = s.query(Membership).filter_by(user_id=guest.id, org_id=org.id).first()
        if not existing:
            s.add(Membership(user_id=guest.id, org_id=org.id, role="member"))
            s.commit()
        return {"invited": login}
    finally:
        s.close()


@app.get("/v1/repos")
def list_repos(ctx=Depends(require_user)):
    _, org = ctx
    s = get_session()
    try:
        rows = s.query(RepoRecord).filter_by(org_id=org.id).all()
        return [
            {
                "id": r.id,
                "name": r.name,
                "github_url": r.github_url,
                "local_path": r.local_path,
                "last_indexed_at": r.last_indexed_at.isoformat() if r.last_indexed_at else None,
                "node_count": r.node_count,
            }
            for r in rows
        ]
    finally:
        s.close()


@app.post("/v1/repos")
def create_repo(body: RepoIn, ctx=Depends(require_user)):
    _, org = ctx
    ok, msg = check_quota(org.id, org.plan, "index")
    s = get_session()
    try:
        n = s.query(RepoRecord).filter_by(org_id=org.id).count()
        from graphcode.saas.usage import PLANS

        if n >= PLANS.get(org.plan, PLANS["free"])["repos"]:
            raise HTTPException(429, "Repo quota exceeded")
        rec = RepoRecord(org_id=org.id, name=body.name, github_url=body.github_url, local_path=body.local_path)
        s.add(rec)
        s.commit()
        s.refresh(rec)
        return {"id": rec.id, "name": rec.name}
    finally:
        s.close()


@app.post("/v1/repos/{repo_id}/index")
def index_repo(repo_id: int, ctx=Depends(require_user)):
    _, org = ctx
    ok, msg = check_quota(org.id, org.plan, "index")
    if not ok:
        raise HTTPException(429, msg)
    s = get_session()
    try:
        rec = s.get(RepoRecord, repo_id)
        if not rec or rec.org_id != org.id:
            raise HTTPException(404, "repo not found")
        path = rec.local_path or rec.github_url
        if rec.github_url.startswith("http") and not rec.local_path:
            dest = Path("data/clones") / str(org.id) / rec.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                import subprocess

                subprocess.run(["git", "clone", "--depth", "1", rec.github_url, str(dest)], check=False)
            path = str(dest)
            rec.local_path = path
        t0 = time.time()
        result = get_index_service().index_repo(path, org_id=str(org.id), repo_id=str(rec.id))
        rec.node_count = int(result.get("counts", {}).get("Function", 0)) + int(
            result.get("counts", {}).get("Module", 0)
        )
        from datetime import datetime, timezone

        rec.last_indexed_at = datetime.now(timezone.utc)
        s.commit()
        ms = int((time.time() - t0) * 1000)
        record_usage(org.id, "index", latency_ms=ms)
        return result
    finally:
        s.close()


@app.get("/v1/queries/blast-radius")
def q_blast(symbol: str, direction: str = "upstream", ctx=Depends(require_user)):
    _, org = ctx
    ok, msg = check_quota(org.id, org.plan, "query")
    if not ok:
        raise HTTPException(429, msg)
    t0 = time.time()
    out = blast_radius(get_index_service().memory, symbol, direction=direction, org_id=str(org.id))
    record_usage(org.id, "query.blast", latency_ms=int((time.time() - t0) * 1000))
    return out


@app.get("/v1/graph/overview")
def q_graph_overview(ctx=Depends(require_user)):
    """File-level dependency map of the currently active repo — every module plus the
    imports between them, sized by contained function/class count. Not gated by the
    per-query quota like the symbol-specific queries below: it's one call per repo
    load, not something a user runs repeatedly."""
    _, org = ctx
    t0 = time.time()
    out = graph_overview(get_index_service().memory, org_id=str(org.id))
    record_usage(org.id, "query.graph_overview", latency_ms=int((time.time() - t0) * 1000))
    return out


@app.get("/v1/graph/suggestions")
def q_graph_suggestions(ctx=Depends(require_user)):
    """"Where do I even start?" — the real gap query autocomplete alone doesn't
    close: autocomplete helps once you know roughly what you're looking for, but a
    user who just indexed an unfamiliar repo doesn't have a name in mind yet. Ranks
    real functions/classes by dependency in-degree (graph centrality, not an LLM
    call) so the most relied-upon parts of the codebase are the first thing shown."""
    _, org = ctx
    t0 = time.time()
    out = suggest_starting_points(get_index_service().memory, org_id=str(org.id))
    record_usage(org.id, "query.graph_suggestions", latency_ms=int((time.time() - t0) * 1000))
    return out


@app.get("/v1/symbols/search")
def q_symbol_search(q: str, ctx=Depends(require_user)):
    """Autocomplete for the query forms — lets a user pick a real, existing symbol
    from a live-searched list instead of blind-typing an exact name and hoping it
    resolves to the thing they meant."""
    _, org = ctx
    results = get_index_service().memory.search(q, org_id=str(org.id))
    return {"results": [{"id": n.id, "label": n.label, **n.props} for n in results]}


@app.get("/v1/ask")
def q_ask(text: str, ctx=Depends(require_user)):
    """The natural-language front door: "what breaks if I change X" instead of
    picking a query type and typing an exact symbol name. Classifies the question via
    the same trained sentence-transformer already used for semantic code search (real
    embedding similarity, not keyword rules — see queries/copilot.py), resolves the
    real symbol(s) it's about, runs the one query that actually answers it, and
    returns a phrased sentence plus the underlying data for the detailed view."""
    _, org = ctx
    ok, msg = check_quota(org.id, org.plan, "query")
    if not ok:
        raise HTTPException(429, msg)
    t0 = time.time()
    out = copilot_ask(get_index_service(), text, org_id=str(org.id))
    record_usage(org.id, "query.ask", latency_ms=int((time.time() - t0) * 1000))
    return out


@app.get("/v1/queries/shortest-path")
def q_path(from_symbol: str, to_symbol: str, ctx=Depends(require_user)):
    _, org = ctx
    ok, msg = check_quota(org.id, org.plan, "query")
    if not ok:
        raise HTTPException(429, msg)
    t0 = time.time()
    out = shortest_path(get_index_service().memory, from_symbol, to_symbol, org_id=str(org.id))
    record_usage(org.id, "query.path", latency_ms=int((time.time() - t0) * 1000))
    return out


@app.get("/v1/queries/call-chain")
def q_chain(symbol: str, ctx=Depends(require_user)):
    _, org = ctx
    t0 = time.time()
    out = call_chain(get_index_service().memory, symbol, org_id=str(org.id))
    record_usage(org.id, "query.chain", latency_ms=int((time.time() - t0) * 1000))
    return out


@app.get("/v1/queries/affected-tests")
def q_affected_tests(symbol: str, ctx=Depends(require_user)):
    _, org = ctx
    ok, msg = check_quota(org.id, org.plan, "query")
    if not ok:
        raise HTTPException(429, msg)
    t0 = time.time()
    out = find_affected_tests(get_index_service().memory, symbol, org_id=str(org.id))
    record_usage(org.id, "query.affected_tests", latency_ms=int((time.time() - t0) * 1000))
    return out


@app.get("/v1/files/source")
def files_source(path: str, start: int = 1, end: int = 60, ctx=Depends(require_user)):
    """Read-only source slice for the web UI's code-preview panels — wraps the
    existing `slice_source` helper (already used by the context compiler), no new
    parsing/resolution logic. Path-traversal-safe: rejects anything resolving outside
    the active repo root, same check as the MCP server's graph_read_file tool."""
    svc = get_index_service()
    root = (svc.last_index or {}).get("root")
    if not root:
        raise HTTPException(400, "no repo indexed yet")
    root_p = Path(root).resolve()
    target = (root_p / path).resolve()
    if root_p not in target.parents and target != root_p:
        raise HTTPException(400, f"path escapes repo root: {path}")
    text = slice_source(root_p, path, start, end, budget_lines=max(1, end - start + 1))
    if not text:
        raise HTTPException(404, f"no such file: {path}")
    return {"path": path, "start": start, "end": end, "text": text}


def _learned_reranker():
    if not settings.enable_learned_rerank:
        return None
    from graphcode.queries.learned_rerank import get_default_reranker

    return get_default_reranker()


def _semantic_hits_for(svc, prompt: str, files: list[str] | None, symbols: list[str] | None, org_id: str):
    query_text = prompt or next(iter((symbols or []) + (files or [])), "")
    if not query_text:
        return None
    hits = semantic_search(svc, query_text, k=40, org_id=org_id)
    return [(h["id"], h["score"]) for h in hits.get("hits") or []]


@app.post("/v1/context/compile")
def q_ctx(body: QueryIn, ctx=Depends(require_user)):
    _, org = ctx
    ok, msg = check_quota(org.id, org.plan, "query")
    if not ok:
        raise HTTPException(429, msg)
    svc = get_index_service()
    semantic_hits = _semantic_hits_for(svc, body.prompt, body.files, body.symbols, org_id=str(org.id))
    text = compile_context(
        svc.memory,
        root=(svc.last_index or {}).get("root"),
        files=body.files,
        symbols=body.symbols,
        prompt=body.prompt,
        max_tokens=body.max_tokens,
        semantic_hits=semantic_hits,
        org_id=str(org.id),
        learned_reranker=_learned_reranker(),
    )
    record_usage(org.id, "query.context", tokens_out=len(text.split()))
    return {"context": text}


@app.post("/v1/context/structured")
def q_ctx_structured(body: QueryIn, ctx=Depends(require_user)):
    """The doc's literal /context contract: seeds, real token accounting, and the
    per-item tier breakdown (0=seed, 1=caller/callee, 2=type, 3=related) instead of
    just the flat rendered string."""
    _, org = ctx
    ok, msg = check_quota(org.id, org.plan, "query")
    if not ok:
        raise HTTPException(429, msg)
    svc = get_index_service()
    semantic_hits = _semantic_hits_for(svc, body.prompt, body.files, body.symbols, org_id=str(org.id))
    bundle = build_context(
        svc.memory,
        root=(svc.last_index or {}).get("root"),
        files=body.files,
        symbols=body.symbols,
        prompt=body.prompt,
        max_tokens=body.max_tokens,
        semantic_hits=semantic_hits,
        org_id=str(org.id),
        learned_reranker=_learned_reranker(),
    )
    record_usage(org.id, "query.context", tokens_out=bundle.used_tokens)
    return {
        "seeds": bundle.seeds,
        "used_tokens": bundle.used_tokens,
        "items": [
            {"qid": it.qid, "path": it.path, "tier": it.tier, "tokens": it.tokens, "text": it.text}
            for it in bundle.items
        ],
        "rendered_prompt": bundle.rendered_prompt,
    }


@app.get("/v1/queries/semantic")
def q_sem(query: str, k: int = 8, ctx=Depends(require_user)):
    _, org = ctx
    return semantic_search(get_index_service(), query, k=k, org_id=str(org.id))


@app.get("/v1/usage")
def usage(ctx=Depends(require_user)):
    _, org = ctx
    return remaining(org.id, org.plan)


@app.post("/v1/keys")
def keys(ctx=Depends(require_user)):
    _, org = ctx
    raw = create_api_key(org.id)
    snippet = {
        "mcpServers": {
            "graph-code": {
                "command": "uv",
                "args": ["run", "python", "-m", "graphcode.mcp.server"],
                "env": {"GRAPHCODE_API_KEY": raw},
            }
        }
    }
    return {"key": raw, "mcp_json": snippet}


@app.post("/v1/billing/checkout")
def billing(plan: str = "pro", ctx=Depends(require_user)):
    _, org = ctx
    return create_checkout_session(plan, org.id)


@app.post("/v1/billing/webhook")
async def stripe_hook(request: Request, stripe_signature: str | None = Header(default=None)):
    payload = await request.body()
    try:
        event = parse_webhook_event(payload, stripe_signature)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    def _upgrade(org_id: int, customer_id: str, plan: str) -> None:
        with get_session() as db:
            org = db.get(Org, org_id)
            if org:
                org.plan = plan
                org.stripe_customer_id = customer_id
                db.commit()

    return handle_webhook_event(event, _upgrade)


@app.post("/v1/watch")
def watch(path: str, ctx=Depends(require_user)):
    return get_watch().start(path, get_index_service(), org_id=str(ctx[1].id))


@app.get("/v1/impact")
def impact():
    s = get_session()
    try:
        users = s.query(User).count()
        orgs = s.query(Org).count()
        repos = s.query(RepoRecord).count()
        from graphcode.saas.models import UsageEvent

        queries = s.query(UsageEvent).filter(UsageEvent.kind.like("query%")).count()
        return {
            "users": users,
            "orgs": orgs,
            "repos_indexed": repos,
            "queries_served": queries,
            "story": "If you change utils.parse_config, Graph-Code shows every controller that CALLS it — even five folders away.",
        }
    finally:
        s.close()


@app.get("/v1/admin")
def admin(ctx=Depends(require_user)):
    user, _ = ctx
    if not is_admin(user.github_id):
        raise HTTPException(403, "admin only")
    return admin_overview()
