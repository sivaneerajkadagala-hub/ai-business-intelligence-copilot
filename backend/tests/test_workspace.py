import io

import pytest
from app.models.user import UserRole
from tests.conftest import auth, create_user

CSV = "date,region,revenue\n" + "\n".join(
    f"2024-01-{d:02d},R{d%3},{d*100}.0" for d in range(1, 11)
)
EVIL_CSV = "name,value\n=cmd|'/c calc'!A1,1\n+1+1,2\n-10,3\n@formula,4\nnormal,5\n"


@pytest.fixture()
def setup(client):
    create_user("ws@test.dev", "Password1!", UserRole.ANALYST)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "ws@test.dev", "password": "Password1!"},
    ).json()["data"]["accessToken"]
    res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("d.csv", io.BytesIO(CSV.encode()))},
        data={"name": "Ws"},
        headers=auth(token),
    )
    return token, res.json()["data"]


# ── Dashboards ────────────────────────────────────────────────────


def test_dashboard_crud_and_widgets(client, setup):
    token, ds = setup
    res = client.post(
        "/api/v1/dashboards",
        json={"name": "Exec Overview", "isShared": True},
        headers=auth(token),
    )
    assert res.status_code == 201
    dash = res.json()["data"]

    widgets = [
        {
            "type": "line", "title": "Revenue trend",
            "config": {"datasetId": ds["id"], "dateColumn": "date",
                       "metricColumn": "revenue", "agg": "sum", "bucket": "day"},
            "position": {"x": 0, "y": 0, "w": 6, "h": 4},
        },
        {
            "type": "bar", "title": "By region",
            "config": {"datasetId": ds["id"], "dimension": "region",
                       "metricColumn": "revenue", "agg": "sum"},
            "position": {"x": 6, "y": 0, "w": 6, "h": 4},
        },
    ]
    res = client.put(
        f"/api/v1/dashboards/{dash['id']}/widgets",
        json={"widgets": widgets}, headers=auth(token),
    )
    assert res.status_code == 200
    assert len(res.json()["data"]) == 2

    detail = client.get(f"/api/v1/dashboards/{dash['id']}", headers=auth(token))
    assert len(detail.json()["data"]["widgets"]) == 2
    assert detail.json()["data"]["widgets"][0]["title"] == "Revenue trend"

    # Summary dashboard counter now counts real dashboards.
    summary = client.get("/api/v1/analytics/summary", headers=auth(token)).json()["data"]
    assert summary["dashboardsCount"] >= 1


def test_dashboard_duplicate(client, setup):
    token, ds = setup
    dash = client.post(
        "/api/v1/dashboards", json={"name": "D1"}, headers=auth(token)
    ).json()["data"]
    client.put(
        f"/api/v1/dashboards/{dash['id']}/widgets",
        json={"widgets": [{"type": "table", "title": "T",
                           "config": {"datasetId": ds["id"]},
                           "position": {"x": 0, "y": 0, "w": 4, "h": 4}}]},
        headers=auth(token),
    )
    res = client.post(
        f"/api/v1/dashboards/{dash['id']}/duplicate", headers=auth(token)
    )
    assert res.status_code == 201
    copy_id = res.json()["data"]["id"]
    detail = client.get(f"/api/v1/dashboards/{copy_id}", headers=auth(token))
    assert len(detail.json()["data"]["widgets"]) == 1


def test_dashboard_viewer_cannot_create(client, setup):
    _, _ = setup
    create_user("vws@test.dev", "Password1!", UserRole.VIEWER)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "vws@test.dev", "password": "Password1!"},
    ).json()["data"]["accessToken"]
    res = client.post("/api/v1/dashboards", json={"name": "X"}, headers=auth(token))
    assert res.status_code == 403


# ── Saved queries ─────────────────────────────────────────────────


def test_saved_query_save_and_run(client, setup):
    token, ds = setup
    # Ask copilot to generate SQL then save it.
    chat = client.post(
        "/api/v1/copilot/chat",
        json={"question": "Total revenue", "datasetId": ds["id"]},
        headers=auth(token),
    ).json()["data"]["message"]

    res = client.post(
        "/api/v1/queries",
        json={"name": "Revenue total", "sql": chat["sql"],
              "datasetId": ds["id"], "isShared": True},
        headers=auth(token),
    )
    assert res.status_code == 201, res.json()
    qid = res.json()["data"]["id"]

    res = client.post(f"/api/v1/queries/{qid}/run", headers=auth(token))
    assert res.status_code == 200
    assert res.json()["data"]["rows"][0]["value"] == pytest.approx(5500.0)

    res = client.get("/api/v1/queries", headers=auth(token))
    assert res.json()["data"][0]["lastRunAt"] is not None


def test_saved_query_rejects_unsafe_sql(client, setup):
    token, ds = setup
    res = client.post(
        "/api/v1/queries",
        json={"name": "Bad", "sql": "DROP TABLE users", "datasetId": ds["id"]},
        headers=auth(token),
    )
    assert res.status_code == 400


def test_saved_query_private_not_listed_for_others(client, setup):
    token, ds = setup
    chat = client.post(
        "/api/v1/copilot/chat",
        json={"question": "Total revenue", "datasetId": ds["id"]},
        headers=auth(token),
    ).json()["data"]["message"]
    client.post(
        "/api/v1/queries",
        json={"name": "Private", "sql": chat["sql"], "datasetId": ds["id"],
              "isShared": False},
        headers=auth(token),
    )
    create_user("other3@test.dev", "Password1!", UserRole.VIEWER)
    other = client.post(
        "/api/v1/auth/login",
        json={"email": "other3@test.dev", "password": "Password1!"},
    ).json()["data"]["accessToken"]
    res = client.get("/api/v1/queries", headers=auth(other))
    assert all(q["name"] != "Private" for q in res.json()["data"])


# ── Reports / export ─────────────────────────────────────────────


def test_csv_export_sanitizes_formulas(client):
    create_user("exp@test.dev", "Password1!", UserRole.ANALYST)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "exp@test.dev", "password": "Password1!"},
    ).json()["data"]["accessToken"]
    res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("e.csv", io.BytesIO(EVIL_CSV.encode()))},
        headers=auth(token),
    )
    ds = res.json()["data"]
    res = client.get(f"/api/v1/datasets/{ds['id']}/export.csv", headers=auth(token))
    assert res.status_code == 200
    body = res.text
    # Dangerous values are quoted with a leading apostrophe.
    assert "'=cmd" in body
    assert "'@formula" in body
    assert "normal" in body


def test_pdf_report_generation_and_download(client, setup):
    token, ds = setup
    res = client.post(
        "/api/v1/reports/generate",
        json={"datasetId": ds["id"], "format": "pdf"},
        headers=auth(token),
    )
    assert res.status_code == 201, res.json()
    report = res.json()["data"]
    assert report["status"] == "ready"

    dl = client.get(f"/api/v1/reports/{report['id']}/download", headers=auth(token))
    assert dl.status_code == 200
    assert dl.content[:5] == b"%PDF-"


def test_report_other_user_cannot_download(client, setup):
    token, ds = setup
    report = client.post(
        "/api/v1/reports/generate",
        json={"datasetId": ds["id"], "format": "pdf"},
        headers=auth(token),
    ).json()["data"]
    create_user("rv@test.dev", "Password1!", UserRole.VIEWER)
    other = client.post(
        "/api/v1/auth/login",
        json={"email": "rv@test.dev", "password": "Password1!"},
    ).json()["data"]["accessToken"]
    res = client.get(f"/api/v1/reports/{report['id']}/download", headers=auth(other))
    assert res.status_code == 404
