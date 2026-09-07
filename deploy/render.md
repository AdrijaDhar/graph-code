# Render.com — $0 deploy, simplest path

Recommended over `oracle-cloud.md` if your goal is "get a real public URL live
today": Render's free tier gives you an HTTPS subdomain automatically
(`your-app.onrender.com`) — no VM to patch, no Caddy/TLS config, no domain to buy.
The trade-off: free-tier services spin down after 15 minutes idle and take ~30s to
wake on the next request (fine for a portfolio/demo tool; not for something you need
always-hot). Oracle's Always-Free VM stays up permanently if that matters more to you
later.

## 1. Backend (FastAPI)

1. Push this repo to your own GitHub (public, since you're open-sourcing it).
2. On [render.com](https://render.com) → **New → Web Service** → connect the repo.
3. Settings:
   - **Runtime**: Python 3
   - **Build command**: `pip install -e .`
   - **Start command**: `uvicorn graphcode.saas.app:app --host 0.0.0.0 --port $PORT`
   - **Instance type**: Free
4. Environment variables (Render dashboard → Environment), no payment tier needed —
   Stripe is entirely optional here and every plan in `saas/usage.py` is already
   priced at $0, so you can skip `STRIPE_SECRET_KEY`/`STRIPE_WEBHOOK_SECRET` outright:
   ```
   PUBLIC_BASE_URL=https://your-app.onrender.com
   CORS_ORIGINS=https://your-frontend.pages.dev
   SESSION_SECRET=<generate a real random string, not the dev default>
   GITHUB_CLIENT_ID=...       # from a GitHub OAuth App, see step 3 below
   GITHUB_CLIENT_SECRET=...
   ```
5. **Persistent data**: Render's free tier has an ephemeral filesystem (wiped on
   redeploy/restart) — add a free Render Disk (Dashboard → your service → Disks) mounted
   at `/opt/render/project/src/data` so `data/rocksdb` and `data/graphcode.db` survive
   restarts. Without this, every redeploy loses all indexed repos and accounts —
   acceptable for a pure demo, not for real usage.

## 2. Frontend (Next.js static export)

Already configured for static export (`output: "export"` in `apps/web/next.config.js`).
Deploy `apps/web` to **Cloudflare Pages** (free, no card required) or Render's static
site product (also free):

```bash
cd apps/web
npm install
NEXT_PUBLIC_API_URL=https://your-app.onrender.com npm run build
```

Point the host at the `out/` directory.

## 3. GitHub OAuth (needed for real sign-in, not the local demo account)

Create an OAuth App at github.com/settings/developers:
- Homepage URL: your frontend's URL
- Callback URL: `https://your-app.onrender.com/v1/auth/github/callback`

Without this configured, `/v1/auth/github` falls back to a local demo account
automatically (see `saas/app.py::auth_github`) — fine for trying it yourself, not for
letting strangers sign in with their own GitHub identity.

## 4. What you still have to do yourself

I can't create accounts or click "deploy" on your behalf. What's left is genuinely
yours to do, in order:
1. Make the GitHub repo public.
2. Create a free Render account, connect the repo, set env vars above.
3. Create a free Cloudflare account, connect `apps/web`, point it at the Render URL.
4. Create the GitHub OAuth App, paste its ID/secret into Render's env vars.
5. Redeploy once both URLs are known to each other (`PUBLIC_BASE_URL` /
   `NEXT_PUBLIC_API_URL` / `CORS_ORIGINS` all need to reference the real final URLs).

Everything code-side is already ready for this — nothing here needs a further code
change, just the account/config steps above.
