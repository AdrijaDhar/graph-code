# Oracle Cloud Always Free (ARM) — $0 deploy

1. Create an Ampere A1 VM in Oracle Cloud Always Free.
2. Open ingress TCP 80 and 443.
3. SSH in and install Docker:

```bash
sudo yum install -y docker git
sudo systemctl enable --now docker
```

4. Clone this repo and start the stack:

```bash
git clone <your-fork> graph-code && cd graph-code
mkdir -p data/rocksdb
docker compose -f deploy/docker-compose.yml up -d
```

5. Point a domain at the VM. Caddy in the compose file issues HTTPS.

6. Frontend: `cd apps/web && npm i && npm run build`, then deploy the `out/` or Next host to **Cloudflare Pages**. Set `NEXT_PUBLIC_API_URL` to `https://your-domain`.

7. Create a free **Supabase** project. Set `DATABASE_URL` to the Postgres URI (or keep SQLite on the VM for demos).

8. GitHub OAuth app: callback `https://api.your-domain/v1/auth/github/callback`.

9. Stripe: test keys only. Never enable live mode until you have a paying user.

## Fallback

If Oracle signup fails, run `docker compose up` on a laptop and expose with **Cloudflare Tunnel** (`cloudflared tunnel`).
