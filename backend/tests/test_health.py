from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_envelope() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"
    assert "database" in body["data"]


def test_unknown_route_returns_error_envelope() -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["errorCode"] == "NOT_FOUND"
