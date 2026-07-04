#!/usr/bin/env bash
# Fresh-volume init: dedicated metadata database for Airflow (Phase 4).
set -euo pipefail
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<'SQL'
SELECT 'CREATE DATABASE airflow OWNER ' || current_user
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'airflow')\gexec
SQL
