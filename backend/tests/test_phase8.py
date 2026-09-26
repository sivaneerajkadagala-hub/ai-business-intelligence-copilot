import io

import pytest
from app.models.user import UserRole
from tests.conftest import auth, create_user

CSV = """date,product,region,revenue
2024-01-05,Widget A,North,500.0
2024-01-06,Widget B,South,250.0
2024-02-08,Widget C,East,99.0
2024-02-09,Widget B,West,350.0
"""


@pytest.fixture()
def setup(client):
    create_user("p8@test.dev", "Password1!", UserRole.ANALYST)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "p8@test.dev", "password": "Password1!"},
    ).json()["data"]["accessToken"]
    res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("d.csv", io.BytesIO(CSV.encode()))},
        data={"name": "P8"},
        headers=auth(token),
    )
    return token, res.json()["data"]


def test_audit_logs_admin_only(client, setup):
    token, ds = setup
    # Generate some auditable activity.
    client.post(
        "/api/v1/copilot/chat",
        json={"question": "total revenue", "datasetId": ds["id"]},
        headers=auth(token),
    )
    create_user("a8@test.dev", "Password1!", UserRole.ADMIN)
    admin = client.post(
        "/api/v1/auth/login",
        json={"email": "a8@test.dev", "password": "Password1!"},
    ).json()["data"]["accessToken"]
    res = client.get("/api/v1/audit-logs?action=copilot", headers=auth(admin))
    assert res.status_code == 200
    items = res.json()["data"]["items"]
    assert any(i["action"] == "copilot.query" for i in items)
    # Non-admin blocked.
    res = client.get("/api/v1/audit-logs", headers=auth(token))
    assert res.status_code == 403


def test_copilot_multiturn_followup(client, setup):
    token, ds = setup
    conv = client.post(
        "/api/v1/copilot/chat",
        json={"question": "Top product by revenue", "datasetId": ds["id"]},
        headers=auth(token),
    ).json()["data"]["conversationId"]
    # Follow-up references nothing explicit — should inherit revenue.
    res = client.post(
        "/api/v1/copilot/chat",
        json={
            "question": "and over time",
            "datasetId": ds["id"],
            "conversationId": conv,
        },
        headers=auth(token),
    )
    assert res.status_code == 200, res.json()
    msg = res.json()["data"]["message"]
    assert msg["chartSpec"]["type"] == "line"
    assert "revenue" in msg["sql"].lower()


def test_pin_message_to_dashboard(client, setup):
    token, ds = setup
    dash = client.post(
        "/api/v1/dashboards", json={"name": "Pinned"}, headers=auth(token)
    ).json()["data"]
    msg = client.post(
        "/api/v1/copilot/chat",
        json={"question": "monthly revenue trend", "datasetId": ds["id"]},
        headers=auth(token),
    ).json()["data"]["message"]
    res = client.post(
        f"/api/v1/copilot/messages/{msg['id']}/pin",
        json={"dashboardId": dash["id"]},
        headers=auth(token),
    )
    assert res.status_code == 201, res.json()
    detail = client.get(
        f"/api/v1/dashboards/{dash['id']}", headers=auth(token)
    ).json()["data"]
    assert len(detail["widgets"]) == 1
    assert detail["widgets"][0]["type"] == "line"
    assert detail["widgets"][0]["config"]["metricColumn"] == "revenue"


def test_pin_rejects_foreign_dashboard(client, setup):
    token, ds = setup
    # Other user creates a private dashboard.
    create_user("d8@test.dev", "Password1!", UserRole.ANALYST)
    other = client.post(
        "/api/v1/auth/login",
        json={"email": "d8@test.dev", "password": "Password1!"},
    ).json()["data"]["accessToken"]
    foreign_dash = client.post(
        "/api/v1/dashboards",
        json={"name": "Not yours", "isShared": False},
        headers=auth(other),
    ).json()["data"]

    msg = client.post(
        "/api/v1/copilot/chat",
        json={"question": "monthly revenue trend", "datasetId": ds["id"]},
        headers=auth(token),
    ).json()["data"]["message"]
    res = client.post(
        f"/api/v1/copilot/messages/{msg['id']}/pin",
        json={"dashboardId": foreign_dash["id"]},
        headers=auth(token),
    )
    assert res.status_code == 404
