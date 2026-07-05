# Deployment — $0/month on Oracle Cloud Always Free

Target: one **Ampere A1 VM** (up to 4 OCPU / 24 GB RAM / 200 GB storage) —
always-on, no cold starts, genuinely free. Everything runs on it via Docker
Compose + two host processes (Ollama, and the intelligence job's venv).

> Signup friction is real: Oracle requires a credit card for identity
> verification (no charge for Always Free usage) and Ampere capacity varies
> by region — budget time for this, don't leave it to the last minute.

## 1. Provision

- Create the VM (Ubuntu 22.04/24.04, Ampere A1, 4 OCPU / 24 GB).
- Open ingress ports: 80/443 (frontend + API via reverse proxy). Keep 5432,
  6379, 8080, 11434 internal.
- Install Docker + Compose plugin, git, python3-venv, Node 20+ (for the
  frontend build), and [Ollama](https://ollama.com/download) (`ollama pull llama3.2`).

## 2. Bring up the stack

```bash
git clone <repo> && cd news-buzz-globe
docker compose -f infra/docker-compose.yml up -d          # Postgres+PostGIS, Redis
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/python -m ingestion.pipeline                     # first load
.venv/bin/dbt build --project-dir dbt --profiles-dir dbt/profiles
.venv/bin/python -m intelligence.job                       # first clustering run
```

Schedule the 15-minute cycle with the provided cron wrapper
(`infra/cron/ingest.sh` — runs pipeline → dbt → clustering), or run the
Airflow profile (`--profile airflow`) if you want the DAG running in
production too. Also schedule the weekly retention job
(`infra/cron/maintenance.sh`, e.g. Sundays 03:00): it rolls raw partitions
older than 90 days into daily grid-cell aggregates (`events_rollup_daily`)
and drops them, keeping storage bounded. Per the project spec, Airflow does **not** need to run 24/7 —
a local demo recording is sufficient.

## 3. Serve the app

```bash
# API (systemd unit or tmux/supervisor)
.venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

# Frontend: build static assets, then serve them + proxy /api via Caddy/nginx
cd frontend && VITE_API_URL=/api npm run build
```

Example Caddyfile (automatic HTTPS):

```
your-domain.example {
    handle_path /api/* {
        reverse_proxy 127.0.0.1:8000
    }
    root * /srv/news-buzz-globe/frontend/dist
    file_server
}
```

## 4. Fallback stack (if Oracle signup fails)

- **Neon** (free tier, 3 GB, PostGIS) for the database — not Supabase
  (pauses after a week idle) or Render Postgres (expires after 30 days).
- **Render free tier** for FastAPI (accepting 15-min spin-down / 30–60 s
  cold starts) with `DATABASE_URL`/`REDIS_URL` env vars; Upstash free Redis
  or simply run without Redis (the API degrades gracefully).
- **Vercel/Netlify** for the static frontend (`VITE_API_URL` → Render URL).
- Summarization: OpenRouter free-tier models as a temporary placeholder via
  `OLLAMA_URL`-compatible shim — explicitly a fallback, not the design.

## Proxied/campus networks (dev-machine note)

On networks that force an HTTP proxy, pass `HTTP_PROXY`/`HTTPS_PROXY`
through to compose (already wired in `infra/docker-compose.yml`) and note
that `infra/cron/ingest.sh` auto-detects the proxy. If `docker pull` is
blocked, images can be fetched over HTTPS and `docker load`-ed as OCI
archives (the compose file accepts `AIRFLOW_IMAGE`/`REDIS_IMAGE` overrides).
