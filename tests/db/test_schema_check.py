import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.db.schema_check import SchemaMismatchError, check_schema
from tests.conftest import make_settings

MODEL = "BAAI/bge-small-en-v1.5"


@pytest.mark.db
def test_ok_when_meta_empty(migrated_conn: psycopg.Connection) -> None:
    assert check_schema(migrated_conn, MODEL, 384) is None


@pytest.mark.db
def test_unmigrated_db_is_not_an_error(db_conn: psycopg.Connection) -> None:
    assert check_schema(db_conn, MODEL, 384) is None


@pytest.mark.db
def test_column_dim_mismatch(migrated_conn: psycopg.Connection) -> None:
    with pytest.raises(SchemaMismatchError) as err:
        check_schema(migrated_conn, MODEL, 768)
    assert "384" in str(err.value)
    assert "768" in str(err.value)
    assert "make db-reset" in str(err.value)


@pytest.mark.db
def test_meta_model_mismatch(migrated_conn: psycopg.Connection) -> None:
    migrated_conn.execute("INSERT INTO embedding_meta (model, dim) VALUES ('other/model', 384)")
    with pytest.raises(SchemaMismatchError) as err:
        check_schema(migrated_conn, MODEL, 384)
    assert "other/model" in str(err.value)
    assert MODEL in str(err.value)


@pytest.mark.db
def test_startup_fails_on_mismatch(
    migrated_conn: psycopg.Connection, test_database_url: str
) -> None:
    app = create_app(make_settings(database_url=test_database_url, embed_dim=768))
    with pytest.raises(SchemaMismatchError):
        with TestClient(app):
            pass


def test_startup_survives_db_down() -> None:
    app = create_app(make_settings(database_url="postgresql://x:y@localhost:1/z"))
    with TestClient(app) as c:
        assert c.get("/health").status_code == 503
