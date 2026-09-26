import io

import pytest
from app.models.user import UserRole
from tests.conftest import auth, create_user

CSV = """order_date,product,region,quantity,revenue
2024-01-05,Widget A,North,10,500.50
2024-01-06,Widget B,South,5,250.00
2024-01-07,Widget A,North,8,400.40
2024-01-08,Widget C,East,3,99.99
2024-01-05,Widget A,North,10,500.50
,Widget B,West,7,350.00
"""

XLSX_CONTENT_TYPES = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _analyst_token(client):
    create_user("analyst@test.dev", "Password1!", UserRole.ANALYST)
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "analyst@test.dev", "password": "Password1!"},
    )
    return res.json()["data"]["accessToken"]


def _upload(client, token, content=CSV, filename="sales.csv", name="Sales"):
    return client.post(
        "/api/v1/datasets/upload",
        files={"file": (filename, io.BytesIO(content.encode() if isinstance(content, str) else content))},
        data={"name": name},
        headers=auth(token),
    )


@pytest.fixture()
def dataset(client):
    token = _analyst_token(client)
    res = _upload(client, token)
    assert res.status_code == 201, res.json()
    return token, res.json()["data"]


def test_upload_csv_creates_ready_dataset(dataset):
    _, ds = dataset
    assert ds["status"] == "ready"
    assert ds["rowCount"] == 6
    assert ds["columnCount"] == 5
    assert ds["qualityScore"] is not None
    assert ds["currentVersionId"]


def test_upload_requires_analyst(client):
    create_user("vw@test.dev", "Password1!", UserRole.VIEWER)
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "vw@test.dev", "password": "Password1!"},
    )
    token = res.json()["data"]["accessToken"]
    res = _upload(client, token)
    assert res.status_code == 403


def test_upload_rejects_bad_extension(client):
    token = _analyst_token(client)
    res = _upload(client, token, filename="notes.txt", content="hello")
    assert res.status_code == 400


def test_upload_rejects_empty_file(client):
    token = _analyst_token(client)
    res = _upload(client, token, content="")
    assert res.status_code == 400


def test_upload_xlsx(client):
    pd = pytest.importorskip("pandas")
    buf = io.BytesIO()
    pd.DataFrame({"a": [1, 2], "b": ["x", "y"]}).to_excel(buf, index=False)
    token = _analyst_token(client)
    res = _upload(client, token, content=buf.getvalue(), filename="t.xlsx")
    assert res.status_code == 201, res.json()
    assert res.json()["data"]["fileType"] == "xlsx"


def test_list_and_get_dataset(client, dataset):
    token, ds = dataset
    res = client.get("/api/v1/datasets", headers=auth(token))
    assert res.status_code == 200
    assert res.json()["data"]["total"] == 1

    res = client.get(f"/api/v1/datasets/{ds['id']}", headers=auth(token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert len(data["versions"]) == 1
    assert data["versions"][0]["kind"] == "original"


def test_profile_returns_column_stats(client, dataset):
    token, ds = dataset
    res = client.get(f"/api/v1/datasets/{ds['id']}/profile", headers=auth(token))
    assert res.status_code == 200
    cols = {c["normalizedName"]: c for c in res.json()["data"]["columns"]}
    assert cols["revenue"]["inferredType"] == "float"
    assert cols["revenue"]["mean"] == pytest.approx(350.2317, abs=0.01)
    assert cols["quantity"]["inferredType"] == "integer"
    assert cols["order_date"]["inferredType"] == "date"
    assert cols["region"]["distinctCount"] == 4
    assert cols["order_date"]["nullCount"] == 1


def test_preview_returns_rows(client, dataset):
    token, ds = dataset
    res = client.get(
        f"/api/v1/datasets/{ds['id']}/preview?page_size=3", headers=auth(token)
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["total"] == 6
    assert len(data["rows"]) == 3
    assert data["pages"] == 2
    assert "revenue" in data["columns"]


def test_clean_creates_new_version_preserving_original(client, dataset):
    token, ds = dataset
    res = client.post(
        f"/api/v1/datasets/{ds['id']}/clean",
        json={
            "operations": [
                {"op": "drop_nulls"},
                {"op": "drop_duplicates"},
            ]
        },
        headers=auth(token),
    )
    assert res.status_code == 201, res.json()
    v2 = res.json()["data"]
    assert v2["versionNo"] == 2
    assert v2["kind"] == "cleaned"
    assert v2["rowCount"] == 4  # 6 − 1 null row − 1 duplicate

    # Dataset points at the new version; original still readable.
    detail = client.get(f"/api/v1/datasets/{ds['id']}", headers=auth(token)).json()["data"]
    assert detail["currentVersionId"] == v2["id"]
    assert len(detail["versions"]) == 2

    v1_id = detail["versions"][0]["id"]
    res = client.get(
        f"/api/v1/datasets/{ds['id']}/preview?version_id={v1_id}", headers=auth(token)
    )
    assert res.json()["data"]["total"] == 6  # original untouched


def test_clean_preview_does_not_persist(client, dataset):
    token, ds = dataset
    res = client.post(
        f"/api/v1/datasets/{ds['id']}/clean/preview",
        json={"operations": [{"op": "drop_nulls"}]},
        headers=auth(token),
    )
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["rowsBefore"] == 6
    assert body["rowsAfter"] == 5
    # nothing persisted
    detail = client.get(f"/api/v1/datasets/{ds['id']}", headers=auth(token)).json()["data"]
    assert len(detail["versions"]) == 1


def test_clean_unknown_column_rejected(client, dataset):
    token, ds = dataset
    res = client.post(
        f"/api/v1/datasets/{ds['id']}/clean",
        json={"operations": [{"op": "drop_nulls", "columns": ["nope"]}]},
        headers=auth(token),
    )
    assert res.status_code == 400


def test_delete_dataset_owner_only(client, dataset):
    token, ds = dataset
    create_user("other@test.dev", "Password1!", UserRole.ANALYST)
    other = client.post(
        "/api/v1/auth/login",
        json={"email": "other@test.dev", "password": "Password1!"},
    ).json()["data"]["accessToken"]

    res = client.delete(f"/api/v1/datasets/{ds['id']}", headers=auth(other))
    assert res.status_code == 403

    res = client.delete(f"/api/v1/datasets/{ds['id']}", headers=auth(token))
    assert res.status_code == 200
    res = client.get(f"/api/v1/datasets/{ds['id']}", headers=auth(token))
    assert res.status_code == 404
