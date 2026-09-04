from __future__ import annotations

import secrets
import time
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import func

from graphcode.config import settings
from graphcode.context.compiler import compile_context
from graphcode.context.pipeline import build_context
from graphcode.indexer import get_index_service
from graphcode.queries.call_chain import call_chain
from graphcode.queries.hybrid import semantic_search
from graphcode.queries.paths import blast_radius, shortest_path
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
        if authorization and authorization.lower().startswith("bearer "):
            from graphcode.saas.auth import org_for_api_key

            token = authorization.split(" ", 1)[1]
            org = org_for_api_key(token)
            if org:
                mem = s.query(Membership).filter_by(org_id=org.id).first()
                user = s.get(User, mem.user_id) if mem else None
                return user, org
        cookie = request.cookies.get("gc_session")
        if cookie:
            payload = verify_session(cookie)
            if payload and payload.startswith("u:"):
                uid = int(payload.split(":")[1])
                user = s.get(User, uid)
                if user:
                    mem = s.query(Membership).filter_by(user_id=user.id).first()
                    org = s.get(Org, mem.org_id) if mem else None
                    return user, org
        # local demo user
        user, org = upsert_github_user("0", "demo", "Demo User")
        return user, org
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
def view_blast(symbol: str = "parse_config"):
    data = blast_radius(get_index_service().memory, symbol, direction="upstream")
    origin = data.get("origin") or {}
    rows = []
    for n in data.get("nodes") or []:
        name = n.get("qualified_name") or n.get("path") or n.get("name")
        via = n.get("via") or "origin"
        rows.append(f"<li><b>{n.get('label')}</b> — {name} <span class='muted'>({via})</span></li>")
    err = data.get("error")
    body = f"<p><b>Error:</b> {err}</p>" if err else f"<ul>{''.join(rows)}</ul>"
    title = origin.get("qualified_name") or symbol
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
        resp = RedirectResponse(url="http://localhost:3000/app")
        resp.set_cookie("gc_session", sign_session(f"u:{user.id}"), httponly=True)
        return resp
    state = secrets.token_urlsafe(16)
    return RedirectResponse(github_login_url(state))


@app.get("/v1/auth/github/callback")
def auth_callback(code: str = "", state: str = ""):
    info = exchange_github_code(code)
    if not info:
        raise HTTPException(400, "oauth failed")
    user, org = upsert_github_user(str(info.get("id")), info.get("login") or "user", info.get("name") or "")
    resp = RedirectResponse(url="http://localhost:3000/app")
    resp.set_cookie("gc_session", sign_session(f"u:{user.id}"), httponly=True)
    return resp


@app.get(" /v1/me".replace(" ", ""))
def me(ctx=Depends(require_user)):
    user, org = ctx
    return {
        "user": {"id": user.id, "login": user.login, "github_id": user.github_id},
        "org": {"id": org.id, "name": org.name, "plan": org.plan},
        "usage": remaining(org.id, org.plan),
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
    out = blast_radius(get_index_service().memory, symbol, direction=direction)
    record_usage(org.id, "query.blast", latency_ms=int((time.time() - t0) * 1000))
    return out


@app.get("/v1/queries/shortest-path")
def q_path(from_symbol: str, to_symbol: str, ctx=Depends(require_user)):
    _, org = ctx
    ok, msg = check_quota(org.id, org.plan, "query")
    if not ok:
        raise HTTPException(429, msg)
    t0 = time.time()
    out = shortest_path(get_index_service().memory, from_symbol, to_symbol)
    record_usage(org.id, "query.path", latency_ms=int((time.time() - t0) * 1000))
    return out


@app.get("/v1/queries/call-chain")
def q_chain(symbol: str, ctx=Depends(require_user)):
    _, org = ctx
    t0 = time.time()
    out = call_chain(get_index_service().memory, symbol)
    record_usage(org.id, "query.chain", latency_ms=int((time.time() - t0) * 1000))
    return out


def _semantic_hits_for(svc, prompt: str, files: list[str] | None, symbols: list[str] | None):
    query_text = prompt or next(iter((symbols or []) + (files or [])), "")
    if not query_text:
        return None
    hits = semantic_search(svc, query_text, k=40)
    return [(h["id"], h["score"]) for h in hits.get("hits") or []]


@app.post("/v1/context/compile")
def q_ctx(body: QueryIn, ctx=Depends(require_user)):
    _, org = ctx
    ok, msg = check_quota(org.id, org.plan, "query")
    if not ok:
        raise HTTPException(429, msg)
    svc = get_index_service()
    semantic_hits = _semantic_hits_for(svc, body.prompt, body.files, body.symbols)
    text = compile_context(
        svc.memory,
        root=(svc.last_index or {}).get("root"),
        files=body.files,
        symbols=body.symbols,
        prompt=body.prompt,
        max_tokens=body.max_tokens,
        semantic_hits=semantic_hits,
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
    semantic_hits = _semantic_hits_for(svc, body.prompt, body.files, body.symbols)
    bundle = build_context(
        svc.memory,
        root=(svc.last_index or {}).get("root"),
        files=body.files,
        symbols=body.symbols,
        prompt=body.prompt,
        max_tokens=body.max_tokens,
        semantic_hits=semantic_hits,
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
