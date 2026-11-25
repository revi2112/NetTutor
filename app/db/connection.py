"""Opening Postgres connections."""

import psycopg

CONNECT_TIMEOUT_SECONDS = 3


def connect(database_url: str) -> psycopg.Connection:
    """Open a connection (autocommit off). Raises psycopg.OperationalError if unreachable."""
    return psycopg.connect(database_url, connect_timeout=CONNECT_TIMEOUT_SECONDS)
