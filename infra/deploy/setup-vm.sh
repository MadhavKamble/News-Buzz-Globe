#!/usr/bin/env bash
# One-shot bootstrap for a fresh Ubuntu 22.04/24.04 VM (Oracle Always Free
# Ampere A1 or any Linux box). Idempotent — safe to re-run.
#
# Usage (on the VM):
#   curl -fsSL https://raw.githubusercontent.com/<user>/<repo>/main/infra/deploy/setup-vm.sh | bash -s -- <git-clone-url>
# or after cloning manually:
#   ./infra/deploy/setup-vm.sh
set -euo pipefail

REPO_URL="${1:-}"
APP_DIR="${HOME}/news-buzz-globe"

log() { echo -e "\n\033[1;36m== $*\033[0m"; }

log "System packages"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  git python3-venv python3-dev build-essential curl ca-certificates \
  docker.io docker-compose-v2 iptables-persistent
sudo usermod -aG docker "$USER" || true

log "Node.js 20 (frontend build)"
if ! command -v node >/dev/null || [ "$(node -v | cut -c2-3)" -lt 20 ]; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - >/dev/null
  sudo apt-get install -y -qq nodejs
fi

log "Caddy (reverse proxy + static frontend)"
if ! command -v caddy >/dev/null; then
  sudo apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | sudo gpg --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  sudo apt-get update -qq && sudo apt-get install -y -qq caddy
fi

log "Ollama + llama3.2 (summarization LLM)"
if ! command -v ollama >/dev/null; then
  curl -fsSL https://ollama.com/install.sh | sh
fi
ollama pull llama3.2

log "Open port 80 (Oracle images ship restrictive iptables)"
sudo iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null \
  || sudo iptables -I INPUT 5 -p tcp --dport 80 -j ACCEPT
sudo netfilter-persistent save >/dev/null

log "Repository"
if [ ! -d "$APP_DIR/.git" ]; then
  [ -n "$REPO_URL" ] || { echo "First run needs the git clone URL as arg 1"; exit 1; }
  git clone "$REPO_URL" "$APP_DIR"
else
  git -C "$APP_DIR" pull --ff-only
fi
cd "$APP_DIR"

log "Database + cache containers"
sudo REDIS_IMAGE=redis:7-alpine docker compose -f infra/docker-compose.yml up -d postgres redis

log "Python environment (torch on ARM takes a few minutes)"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e .

log "Waiting for Postgres"
until sudo docker exec nbg-postgres pg_isready -U nbg -d newsbuzz >/dev/null 2>&1; do sleep 2; done

log "First data cycle (pipeline -> dbt -> stories)"
.venv/bin/python -m ingestion.pipeline
.venv/bin/dbt build --project-dir dbt --profiles-dir dbt/profiles
.venv/bin/python -m intelligence.job

log "Frontend build"
cd frontend && npm ci --no-audit --no-fund && VITE_API_URL=/api npm run build && cd ..

log "systemd service for the API"
sudo tee /etc/systemd/system/nbg-api.service >/dev/null <<UNIT
[Unit]
Description=News Buzz Globe API
After=network.target docker.service

[Service]
User=${USER}
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/.venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now nbg-api

log "Caddy site"
sudo cp infra/deploy/Caddyfile /etc/caddy/Caddyfile
sudo sed -i "s|__APP_DIR__|${APP_DIR}|" /etc/caddy/Caddyfile
sudo systemctl reload caddy

log "Cron: 15-min ingest + weekly retention"
( crontab -l 2>/dev/null | grep -vE 'ingest\.sh|maintenance\.sh' ;
  echo "*/15 * * * * ${APP_DIR}/infra/cron/ingest.sh" ;
  echo "0 3 * * 0 ${APP_DIR}/infra/cron/maintenance.sh" ) | crontab -

log "Done"
echo "App:    http://$(curl -s ifconfig.me)/"
echo "API:    http://$(curl -s ifconfig.me)/api/health"
echo "Remember: open ingress TCP 80 in the Oracle VCN security list too."
