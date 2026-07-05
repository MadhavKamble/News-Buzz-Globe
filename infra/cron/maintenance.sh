#!/usr/bin/env bash
# Weekly retention/rollup: downsample raw_events partitions older than 90
# days into events_rollup_daily, then drop them. Install with:
#   ( crontab -l 2>/dev/null; echo '0 3 * * 0 /path/to/repo/infra/cron/maintenance.sh' ) | crontab -
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="${REPO_DIR}/logs"
mkdir -p "${LOG_DIR}"

cd "${REPO_DIR}"
"${REPO_DIR}/.venv/bin/python" -m ingestion.maintenance >> "${LOG_DIR}/maintenance.log" 2>&1
