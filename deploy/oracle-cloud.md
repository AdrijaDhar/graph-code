# Oracle Cloud Always Free (ARM) — $0 deploy

1. Create an Ampere A1 VM in Oracle Cloud Always Free.
2. Open ingress TCP 80 and 443.
3. SSH in and install Docker:

```bash
sudo yum install -y docker git
sudo systemctl enable --now docker
```

4. Clone this repo and set up secrets:

```bash
git clone <your-fork> graph-code && cd graph-code
mkdir -p data/rocksdb
cp deploy/api.env.example deploy/api.env
```

Edit `deploy/api.env` (gitignored, never commit it) with real values, then start the stack:

```bash
docker compose -f deploy/docker-compose.yml up -d
```

5. Point a domain at the VM. Caddy in the compose file issues HTTPS.

6. Frontend: `cd apps/web && npm i && npm run build`, then deploy the `out/` or Next host to **Cloudflare Pages**. Set `NEXT_PUBLIC_API_URL` to `https://your-domain`.

7. **Database** — create a free **Supabase** project, copy its Postgres connection string, and set it in `deploy/api.env`:

```bash
echo "DATABASE_URL=postgresql://postgres:PASSWORD@db.PROJECT.supabase.co:5432/postgres" >> deploy/api.env
```

   Or leave `DATABASE_URL` unset in `deploy/api.env` to keep the compose file's default SQLite volume for demos.

8. **GitHub OAuth** — create an OAuth app at github.com/settings/developers with callback `https://api.your-domain/v1/auth/github/callback`, then:

```bash
cat >> deploy/api.env <<'EOF'
GITHUB_CLIENT_ID=your-client-id
GITHUB_CLIENT_SECRET=your-client-secret
PUBLIC_BASE_URL=https://api.your-domain
EOF
```

9. **Stripe** — test keys only; never enable live mode until you have a paying user. From the Stripe dashboard (test mode) grab the secret key, then create a webhook endpoint at `https://api.your-domain/v1/billing/webhook` for the `checkout.session.completed` event and grab its signing secret:

```bash
cat >> deploy/api.env <<'EOF'
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
EOF
```

After editing `deploy/api.env`, apply it with:

```bash
docker compose -f deploy/docker-compose.yml up -d --force-recreate api
```

## Fallback

If Oracle signup fails, run `docker compose up` on a laptop and expose with **Cloudflare Tunnel** (`cloudflared tunnel`).
