from app.models.user import UserRole
from tests.conftest import auth, create_user


def _login(client, email: str, password: str) -> str:
    res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return res.json()["data"]["accessToken"]


def test_users_requires_admin(admin_client):
    client, token = admin_client
    res = client.get("/api/v1/users", headers=auth(token))
    assert res.status_code == 200
    assert res.json()["data"]["total"] == 1


def test_users_forbidden_for_analyst_and_viewer(client):
    create_user("an@test.dev", "Password1!", UserRole.ANALYST)
    create_user("vw@test.dev", "Password1!", UserRole.VIEWER)
    for email in ("an@test.dev", "vw@test.dev"):
        token = _login(client, email, "Password1!")
        res = client.get("/api/v1/users", headers=auth(token))
        assert res.status_code == 403, email
        assert res.json()["errorCode"] == "FORBIDDEN"


def test_users_unauthenticated(client):
    assert client.get("/api/v1/users").status_code == 401


def test_admin_can_create_user(admin_client):
    client, token = admin_client
    res = client.post(
        "/api/v1/users",
        json={"email": "made@test.dev", "password": "Password1!", "fullName": "Made", "role": "viewer"},
        headers=auth(token),
    )
    assert res.status_code == 201
    assert res.json()["data"]["role"] == "viewer"


def test_admin_can_update_role(admin_client):
    client, token = admin_client
    user = create_user("u@test.dev", "Password1!", UserRole.VIEWER)
    res = client.patch(
        f"/api/v1/users/{user.id}/role",
        json={"role": "analyst"},
        headers=auth(token),
    )
    assert res.status_code == 200
    assert res.json()["data"]["role"] == "analyst"


def test_admin_cannot_demote_self(admin_client):
    client, token = admin_client
    me = client.get("/api/v1/auth/me", headers=auth(token)).json()["data"]
    res = client.patch(
        f"/api/v1/users/{me['id']}/role",
        json={"role": "viewer"},
        headers=auth(token),
    )
    assert res.status_code == 400


def test_deactivated_user_cannot_login(admin_client):
    client, token = admin_client
    user = create_user("u@test.dev", "Password1!", UserRole.ANALYST)
    res = client.delete(f"/api/v1/users/{user.id}", headers=auth(token))
    assert res.status_code == 200
    res = client.post("/api/v1/auth/login", json={"email": "u@test.dev", "password": "Password1!"})
    assert res.status_code == 403


def test_audit_trail_written(client):
    create_user("u@test.dev", "Password1!", UserRole.ANALYST)
    client.post("/api/v1/auth/login", json={"email": "u@test.dev", "password": "Password1!"})
    from tests.conftest import TestingSessionLocal
    from app.models.audit import AuditLog
    from sqlalchemy import select

    db = TestingSessionLocal()
    actions = [r.action for r in db.scalars(select(AuditLog)).all()]
    db.close()
    assert "auth.login" in actions
