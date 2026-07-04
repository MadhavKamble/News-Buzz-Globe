-- Runs once on first container start (fresh volume). The postgis/postgis
-- image already ships the extension; this makes it explicit and idempotent.
CREATE EXTENSION IF NOT EXISTS postgis;
