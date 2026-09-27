"""Idempotent DB bootstrap for hosted Postgres (Railway et al.).

Replicates what database/init/01_init.sh does in docker-compose —
the Railway Postgres image never runs those entrypoint scripts.
Must run BEFORE alembic upgrade / seed in the start command.
"""

import re

from sqlalchemy import create_engine, text

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    for ident in (settings.BI_READER_USER, settings.POSTGRES_DB):
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", ident):
            raise ValueError(f"unsafe identifier: {ident!r}")
    reader = settings.BI_READER_USER

    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS data"))
        exists = conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": reader}
        ).scalar()
        if not exists:
            conn.execute(text(f"CREATE ROLE {reader} LOGIN PASSWORD :p"), {"p": settings.BI_READER_PASSWORD})
        conn.execute(text(f"GRANT CONNECT ON DATABASE {settings.POSTGRES_DB} TO {reader}"))
        conn.execute(text(f"GRANT USAGE ON SCHEMA data TO {reader}"))
        conn.execute(text(f"GRANT SELECT ON ALL TABLES IN SCHEMA data TO {reader}"))
        conn.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA data GRANT SELECT ON TABLES TO {reader}"))
    print("[bootstrap] data schema + bi_reader role ready")


if __name__ == "__main__":
    main()
