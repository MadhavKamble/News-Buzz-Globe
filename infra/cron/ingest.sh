#!/usr/bin/env bash
# Cron wrapper for the GDELT ingestion pipeline (Phase 1 scheduling; replaced
# by Airflow in Phase 4). Install with:
#   ( crontab -l 2>/dev/null; echo '*/15 * * * * /path/to/repo/infra/cron/ingest.sh' ) | crontab -
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="${REPO_DIR}/logs"
mkdir -p "${LOG_DIR}"

# Cron strips shell env. On networks that force an HTTP proxy (e.g. campus),
# export it when reachable so GDELT fetches work; harmless elsewhere.
PROXY_URL="${NBG_PROXY_URL:-http://172.31.2.4:8080/}"
PROXY_HOSTPORT="${PROXY_URL#http://}"; PROXY_HOSTPORT="${PROXY_HOSTPORT%%/*}"
if timeout 2 bash -c "</dev/tcp/${PROXY_HOSTPORT/:/\/}" 2>/dev/null; then
  export HTTP_PROXY="$PROXY_URL" HTTPS_PROXY="$PROXY_URL"
  export http_proxy="$PROXY_URL" https_proxy="$PROXY_URL"
  export NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1
fi

cd "${REPO_DIR}"
"${REPO_DIR}/.venv/bin/python" -m ingestion.pipeline >> "${LOG_DIR}/ingestion.log" 2>&1
