import io
import uuid

import pytest
from app.models.user import UserRole
from tests.conftest import auth, create_user

# 30 days, one obvious spike on day 20.
ROWS = "date,region,revenue\n" + "\n".join(
    f"2024-03-{d:02d},R{i%3},{800 if i != 19 else 8000}.0" for i, d in enumerate(range(1, 31))
)


@pytest.fixture()
def setup(client):
    create_user("ins@test.dev", "Password1!", UserRole.ANALYST)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "ins@test.dev", "password": "Password1!"},
    ).json()["data"]["accessToken"]
    res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("d.csv", io.BytesIO(ROWS.encode()))},
        data={"name": "Spiky"},
        headers=auth(token),
    )
    assert res.status_code == 201, res.json()
    return token, res.json()["data"]


def test_anomalies_finds_injected_spike(client, setup):
    token, ds = setup
    res = client.get(
        f"/api/v1/insights/anomalies?dataset_id={ds['id']}"
        "&date_column=date&metric_column=revenue&bucket=day",
        headers=auth(token),
    )
    assert res.status_code == 200, res.json()
    d = res.json()["data"]
    assert d["points"] == 30
    assert any(a["t"] == "2024-03-20" and a["direction"] == "spike" for a in d["anomalies"])


def test_anomalies_rejects_short_series(client):
    create_user("s@test.dev", "Password1!", UserRole.ANALYST)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "s@test.dev", "password": "Password1!"},
    ).json()["data"]["accessToken"]
    res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("s.csv", io.BytesIO(b"date,v\n2024-01-01,5\n2024-01-02,6\n"))},
        headers=auth(token),
    )
    ds = res.json()["data"]
    res = client.get(
        f"/api/v1/insights/anomalies?dataset_id={ds['id']}&date_column=date&metric_column=v",
        headers=auth(token),
    )
    assert res.status_code == 400


def test_forecast_returns_horizon_with_ci(client, setup):
    token, ds = setup
    res = client.post(
        "/api/v1/insights/forecast",
        json={
            "datasetId": ds["id"],
            "dateColumn": "date",
            "metricColumn": "revenue",
            "bucket": "day",
            "horizon": 5,
        },
        headers=auth(token),
    )
    assert res.status_code == 200, res.json()
    d = res.json()["data"]
    assert len(d["forecast"]) == 5
    assert d["method"] in ("holt_winters", "holt_linear", "naive")
    assert len(d["history"]) == 30
    for p in d["forecast"]:
        assert p["lower"] <= p["forecast"] <= p["upper"]


def test_insights_generate_and_idempotent(client, setup):
    token, ds = setup
    res = client.post(
        f"/api/v1/insights/generate?dataset_id={ds['id']}", headers=auth(token)
    )
    assert res.status_code == 200, res.json()
    first = res.json()["data"]
    assert len(first) >= 2
    types = {i["type"] for i in first}
    assert "trend" in types or "anomaly" in types

    # Re-generating replaces rather than duplicates.
    res = client.post(
        f"/api/v1/insights/generate?dataset_id={ds['id']}", headers=auth(token)
    )
    second = res.json()["data"]
    assert len(second) == len(first)

    res = client.get(f"/api/v1/insights?dataset_id={ds['id']}", headers=auth(token))
    assert len(res.json()["data"]) == len(first)


def test_generate_requires_analyst(client, setup):
    _, ds = setup
    create_user("vins@test.dev", "Password1!", UserRole.VIEWER)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "vins@test.dev", "password": "Password1!"},
    ).json()["data"]["accessToken"]
    res = client.post(
        f"/api/v1/insights/generate?dataset_id={ds['id']}", headers=auth(token)
    )
    assert res.status_code == 403


def test_copilot_anomaly_intent(client, setup):
    token, ds = setup
    res = client.post(
        "/api/v1/copilot/chat",
        json={"question": "Any anomalies in revenue?", "datasetId": ds["id"]},
        headers=auth(token),
    )
    assert res.status_code == 200, res.json()
    msg = res.json()["data"]["message"]
    assert msg["chartSpec"]["type"] == "anomaly"
    assert "anomal" in msg["content"].lower()
    rows = msg["resultSnapshot"]["rows"]
    assert any(r["t"] == "2024-03-20" for r in rows)


def test_copilot_forecast_intent(client, setup):
    token, ds = setup
    res = client.post(
        "/api/v1/copilot/chat",
        json={"question": "Forecast next 5 days of revenue", "datasetId": ds["id"]},
        headers=auth(token),
    )
    assert res.status_code == 200, res.json()
    msg = res.json()["data"]["message"]
    assert msg["chartSpec"]["type"] == "forecast"
    assert len(msg["resultSnapshot"]["rows"]) == 5
    assert "forecast" in msg["resultSnapshot"]["columns"]
