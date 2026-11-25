"""Apply plain SQL migrations in filename order.

Why plain SQL instead of Alembic: there are no ORM models to autogenerate from, the whole
mechanism fits on one screen, and it is easy to explain. Each file runs in its own transaction
together with its `schema_migrations` row, so a failing file leaves nothing half-applied.

The literal `{embed_dim}` in a file is replaced with the configured embedding dimension.
"""

from pathlib import Path

import psycopg

from app.config import get_settings
from app.db.connection import connect

DEFAULT_DIR = Path(__file__).parent / "migrations"


def apply_migrations(
    conn: psycopg.Connection, embed_dim: int, migrations_dir: Path = DEFAULT_DIR
) -> list[str]:
    """Apply every not-yet-applied migration; return the filenames applied this run."""
    with conn.transaction():
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " filename text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        done = {row[0] for row in conn.execute("SELECT filename FROM schema_migrations")}

    applied: list[str] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        if path.name in done:
            continue
        script = path.read_text().replace("{embed_dim}", str(embed_dim))
        with conn.transaction():
            conn.execute(script.encode())
            conn.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,))
        applied.append(path.name)
    return applied


def main() -> None:
    settings = get_settings()
    with connect(settings.database_url) as conn:
        applied = apply_migrations(conn, embed_dim=settings.embed_dim)
    print("applied:", ", ".join(applied) if applied else "nothing (up to date)")


if __name__ == "__main__":
    main()
