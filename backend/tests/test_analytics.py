import io
import uuid

import pytest
from app.models.user import UserRole
from tests.conftest import auth, create_user

CSV = """date,region,revenue
2024-01-05,North,100.0
2024-01-06,South,50.0
2024-02-10,North,200.0
2024-03-15,East,300.0
"""


@pytest.fixture()
def setup(client):
    create_user("an@test.dev", "Password1!", UserRole.ANALYST)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "an@test.dev", "password": "Password1!"},
    ).json()["data"]["accessToken"]
    res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("d.csv", io.BytesIO(CSV.encode()))},
        data={"name": "Rev"},
        headers=auth(token),
    )
    assert res.status_code == 201, res.json()
    return token, res.json()["data"]


def test_series_monthly(client, setup):
    token, ds = setup
    res = client.get(
        f"/api/v1/analytics/series?dataset_id={ds['id']}"
        "&date_column=date&metric_column=revenue&agg=sum&bucket=month",
        headers=auth(token),
    )
    assert res.status_code == 200, res.json()
    points = res.json()["data"]["points"]
    assert len(points) == 3
    values = {p["t"]: p["value"] for p in points}
    assert values["2024-01"] == pytest.approx(150.0)
    assert values["2024-02"] == pytest.approx(200.0)
    assert values["2024-03"] == pytest.approx(300.0)


def test_series_date_filter(client, setup):
    token, ds = setup
    res = client.get(
        f"/api/v1/analytics/series?dataset_id={ds['id']}"
        "&date_column=date&metric_column=revenue&agg=sum&bucket=month"
        "&from=2024-02-01&to=2024-02-29",
        headers=auth(token),
    )
    points = res.json()["data"]["points"]
    assert len(points) == 1
    assert points[0]["value"] == pytest.approx(200.0)


def test_series_rejects_bad_column(client, setup):
    token, ds = setup
    res = client.get(
        f"/api/v1/analytics/series?dataset_id={ds['id']}"
        "&date_column=region&metric_column=revenue&agg=sum&bucket=month",
        headers=auth(token),
    )
    assert res.status_code == 400

    res = client.get(
        f"/api/v1/analytics/series?dataset_id={ds['id']}"
        "&date_column=date&metric_column=region&agg=sum&bucket=month",
        headers=auth(token),
    )
    assert res.status_code == 400  # sum over string column


def test_breakdown_by_region(client, setup):
    token, ds = setup
    res = client.get(
        f"/api/v1/analytics/breakdown?dataset_id={ds['id']}"
        "&dimension=region&metric_column=revenue&agg=sum",
        headers=auth(token),
    )
    assert res.status_code == 200
    items = res.json()["data"]["items"]
    assert items[0]["label"] == "North"
    assert items[0]["value"] == pytest.approx(300.0)
    assert {i["label"] for i in items} == {"North", "East", "South"}


def test_breakdown_count(client, setup):
    token, ds = setup
    res = client.get(
        f"/api/v1/analytics/breakdown?dataset_id={ds['id']}&dimension=region&agg=count",
        headers=auth(token),
    )
    items = res.json()["data"]["items"]
    assert items[0]["value"] == 2  # North has 2 rows


def test_kpi_crud_and_value(client, setup):
    token, ds = setup
    res = client.post(
        "/api/v1/analytics/kpis",
        json={
            "name": "Total Revenue",
            "datasetId": ds["id"],
            "formula": {
                "aggregation": "sum",
                "column": "revenue",
                "dateColumn": "date",
            },
            "target": 1000.0,
            "unit": "$",
        },
        headers=auth(token),
    )
    assert res.status_code == 201, res.json()
    kpi = res.json()["data"]

    res = client.get(f"/api/v1/analytics/kpis/{kpi['id']}/value", headers=auth(token))
    assert res.status_code == 200
    val = res.json()["data"]
    assert val["value"] == pytest.approx(650.0)
    assert val["progressPct"] == pytest.approx(65.0)
    assert val["unit"] == "$"

    res = client.delete(f"/api/v1/analytics/kpis/{kpi['id']}", headers=auth(token))
    assert res.status_code == 200
    res = client.get(f"/api/v1/analytics/kpis/{kpi['id']}/value", headers=auth(token))
    assert res.status_code == 404


def test_kpi_create_requires_analyst(client, setup):
    _, ds = setup
    create_user("v@test.dev", "Password1!", UserRole.VIEWER)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "v@test.dev", "password": "Password1!"},
    ).json()["data"]["accessToken"]
    res = client.post(
        "/api/v1/analytics/kpis",
        json={
            "name": "X",
            "datasetId": ds["id"],
            "formula": {"aggregation": "sum", "column": "revenue"},
        },
        headers=auth(token),
    )
    assert res.status_code == 403


def test_summary_shape(client, setup):
    token, _ = setup
    res = client.get("/api/v1/analytics/summary", headers=auth(token))
    assert res.status_code == 200
    d = res.json()["data"]
    assert d["datasetsCount"] == 1
    assert d["totalRecords"] == 4
    assert isinstance(d["recentActivity"], list)
    assert d["kpis"] == []


def test_unknown_dataset_404(client, setup):
    token, _ = setup
    res = client.get(
        f"/api/v1/analytics/series?dataset_id={uuid.uuid4()}"
        "&date_column=date&agg=count&bucket=month",
        headers=auth(token),
    )
    assert res.status_code == 404
