import io
import time

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, text
from app.models.user import UserRole
from tests.conftest import auth, create_user

CSV = "date,region,revenue\n" + "\n".join(
    f"2024-01-{d:02d},R{d%3},{d*100}.0" for d in range(1, 8)
)


@pytest.fixture()
def setup(client):
    create_user("p9@test.dev", "Password1!", UserRole.ANALYST)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "p9@test.dev", "password": "Password1!"},
    ).json()["data"]["accessToken"]
    return token


def _wait_ready(client, token, ds_id, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        res = client.get(f"/api/v1/datasets/{ds_id}", headers=auth(token))
        status = res.json()["data"]["status"]
        if status in ("ready", "failed"):
            return status
        time.sleep(0.3)
    return "timeout"


def test_async_upload_completes_and_notifies(client, setup):
    token = setup
    res = client.post(
        "/api/v1/datasets/upload?async=true",
        files={"file": ("a.csv", io.BytesIO(CSV.encode()))},
        headers=auth(token),
    )
    assert res.status_code == 201, res.json()
    ds = res.json()["data"]
    status = _wait_ready(client, token, ds["id"])
    assert status == "ready"

    # Import record transitions + notification emitted.
    imports = client.get(
        f"/api/v1/datasets/{ds['id']}/imports", headers=auth(token)
    ).json()["data"]
    assert imports[0]["status"] == "success"

    unread = client.get("/api/v1/notifications/unread-count", headers=auth(token))
    assert unread.json()["data"]["count"] >= 1
    notes = client.get("/api/v1/notifications", headers=auth(token)).json()["data"]
    assert any(n["type"] == "ingest.success" for n in notes)

    client.post(f"/api/v1/notifications/{notes[0]['id']}/read", headers=auth(token))
    client.post("/api/v1/notifications/read-all", headers=auth(token))
    unread = client.get("/api/v1/notifications/unread-count", headers=auth(token))
    assert unread.json()["data"]["count"] == 0


def test_sync_upload_still_works(client, setup):
    token = setup
    res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("s.csv", io.BytesIO(CSV.encode()))},
        headers=auth(token),
    )
    assert res.status_code == 201
    assert res.json()["data"]["status"] == "ready"


def _make_source_db(path) -> str:
    eng = create_engine(f"sqlite+pysqlite:///{path}")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE orders (id INTEGER, product TEXT, amount REAL)"))
        conn.execute(
            text("INSERT INTO orders VALUES (1,'a',10.5),(2,'b',20.5),(3,'c',30.5)")
        )
    eng.dispose()
    return f"sqlite+pysqlite:///{path}"


def test_source_preview_and_import(client, setup, tmp_path):
    token = setup
    url = _make_source_db(tmp_path / "src.db")

    res = client.post("/api/v1/datasets/source/preview", json={"url": url}, headers=auth(token))
    assert res.status_code == 200, res.json()
    assert any(t["table"] == "orders" for t in res.json()["data"]["tables"])

    res = client.post(
        "/api/v1/datasets/import-source",
        json={"url": url, "table": "orders", "name": "RemoteOrders"},
        headers=auth(token),
    )
    assert res.status_code == 201, res.json()
    ds = res.json()["data"]
    assert ds["status"] == "ready"
    assert ds["rowCount"] == 3

    # Provenance recorded on the import record.
    imports = client.get(f"/api/v1/datasets/{ds['id']}/imports", headers=auth(token))
    prov = imports.json()["data"][0]["source"]
    assert prov["scheme"].startswith("sqlite")


def test_source_query_import_and_validation(client, setup, tmp_path):
    token = setup
    url = _make_source_db(tmp_path / "src2.db")
    res = client.post(
        "/api/v1/datasets/import-source",
        json={"url": url, "query": "SELECT product, amount FROM orders WHERE amount > 15"},
        headers=auth(token),
    )
    assert res.status_code == 201
    assert res.json()["data"]["rowCount"] == 2

    # DDL/DML rejected.
    res = client.post(
        "/api/v1/datasets/import-source",
        json={"url": url, "query": "DROP TABLE orders"},
        headers=auth(token),
    )
    assert res.status_code == 400

    # Unknown scheme rejected.
    res = client.post(
        "/api/v1/datasets/import-source",
        json={"url": "mysql://u:p@h/db", "table": "orders"},
        headers=auth(token),
    )
    assert res.status_code == 400


def test_source_viewer_denied(client, setup, tmp_path):
    create_user("vp9@test.dev", "Password1!", UserRole.VIEWER)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "vp9@test.dev", "password": "Password1!"},
    ).json()["data"]["accessToken"]
    url = _make_source_db(tmp_path / "src3.db")
    res = client.post(
        "/api/v1/datasets/import-source",
        json={"url": url, "table": "orders"}, headers=auth(token),
    )
    assert res.status_code == 403
