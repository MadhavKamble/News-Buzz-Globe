"""Engine/session helpers shared by ingestion and backend."""

import os

from sqlalchemy import Engine, create_engine


def database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg2://nbg:nbg_dev_password@localhost:5432/newsbuzz",
    )


def get_engine(url: str | None = None) -> Engine:
    return create_engine(url or database_url(), pool_pre_ping=True)
