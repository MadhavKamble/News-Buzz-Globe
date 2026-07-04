#!/usr/bin/env bash
# Cron wrapper for the GDELT ingestion pipeline (Phase 1 scheduling; replaced
# by Airflow in Phase 4). Install with:
#   ( crontab -l 2>/dev/null; echo '*/15 * * * * /path/to/repo/infra/cron/ingest.sh' ) | crontab -
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="${REPO_DIR}/logs"
mkdir -p "${LOG_DIR}"

cd "${REPO_DIR}"
"${REPO_DIR}/.venv/bin/python" -m ingestion.pipeline >> "${LOG_DIR}/ingestion.log" 2>&1
