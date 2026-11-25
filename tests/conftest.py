"""Shared fixtures. DB tests use a throwaway `nettutor_test` database on the compose Postgres."""

from collections.abc import Iterator
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from app.api.main import create_app
from app.config import Settings

TEST_DB_NAME = "nettutor_test"


def _with_db(url: str, db_name: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{db_name}"))


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg, arg-type]


@pytest.fixture(scope="session")
def test_database_url() -> str:
    base_url = make_settings().database_url
    try:
        admin = psycopg.connect(_with_db(base_url, "postgres"), autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres is not reachable; run `make db-up` to run DB tests")
    with admin:
        name = sql.Identifier(TEST_DB_NAME)
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(name))
        admin.execute(sql.SQL("CREATE DATABASE {}").format(name))
    return _with_db(base_url, TEST_DB_NAME)


@pytest.fixture
def client(test_database_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(make_settings(database_url=test_database_url))) as c:
        yield c
