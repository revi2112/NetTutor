import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from tests.conftest import make_settings

DOWN_URL = "postgresql://nettutor:hunter2@localhost:1/nope"


@pytest.mark.db
def test_health_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}


def test_health_db_down() -> None:
    with TestClient(create_app(make_settings(database_url=DOWN_URL))) as c:
        response = c.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "db": "unreachable"}
    assert "hunter2" not in response.text
    assert "localhost:1" not in response.text
