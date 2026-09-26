from app.models.user import UserRole
from tests.conftest import auth, create_user


def test_register_creates_user(client):
    res = client.post(
        "/api/v1/auth/register",
        json={"email": "New@Test.dev", "password": "Password1!", "fullName": "New User"},
    )
    assert res.status_code == 201
    data = res.json()["data"]["user"]
    assert data["email"] == "new@test.dev"  # normalized
    assert data["role"] == "analyst"
    assert "password" not in str(res.json()).lower()


def test_register_duplicate_rejected(client):
    create_user("dup@test.dev", "Password1!", UserRole.VIEWER)
    res = client.post(
        "/api/v1/auth/register",
        json={"email": "dup@test.dev", "password": "Password1!", "fullName": "Dup"},
    )
    assert res.status_code == 409
    assert res.json()["errorCode"] == "CONFLICT"


def test_register_short_password_rejected(client):
    res = client.post(
        "/api/v1/auth/register",
        json={"email": "x@test.dev", "password": "short", "fullName": "X"},
    )
    assert res.status_code == 422


def test_login_success_sets_access_and_refresh(client):
    create_user("u@test.dev", "Password1!", UserRole.ANALYST)
    res = client.post("/api/v1/auth/login", json={"email": "u@test.dev", "password": "Password1!"})
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["accessToken"]
    assert body["user"]["role"] == "analyst"
    assert "bi_refresh" in res.cookies


def test_login_wrong_password(client):
    create_user("u@test.dev", "Password1!", UserRole.ANALYST)
    res = client.post("/api/v1/auth/login", json={"email": "u@test.dev", "password": "wrong-pass"})
    assert res.status_code == 401


def test_me_requires_auth(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_returns_profile(client):
    create_user("u@test.dev", "Password1!", UserRole.ANALYST)
    res = client.post("/api/v1/auth/login", json={"email": "u@test.dev", "password": "Password1!"})
    token = res.json()["data"]["accessToken"]
    me = client.get("/api/v1/auth/me", headers=auth(token))
    assert me.status_code == 200
    assert me.json()["data"]["email"] == "u@test.dev"


def test_refresh_rotates_and_detects_reuse(client):
    create_user("u@test.dev", "Password1!", UserRole.ANALYST)
    res = client.post("/api/v1/auth/login", json={"email": "u@test.dev", "password": "Password1!"})
    old_refresh = res.cookies.get("bi_refresh")

    r1 = client.post("/api/v1/auth/refresh")
    assert r1.status_code == 200
    new_refresh = r1.cookies.get("bi_refresh")
    assert new_refresh != old_refresh

    # Replaying the rotated token must fail AND nuke the whole family.
    r2 = client.post("/api/v1/auth/refresh", cookies={"bi_refresh": old_refresh})
    assert r2.status_code == 401

    # The valid successor is also dead now — theft containment.
    r3 = client.post("/api/v1/auth/refresh", cookies={"bi_refresh": new_refresh})
    assert r3.status_code == 401


def test_forgot_and_reset_password_flow(client):
    create_user("u@test.dev", "Password1!", UserRole.ANALYST)
    res = client.post("/api/v1/auth/forgot-password", json={"email": "u@test.dev"})
    assert res.status_code == 200
    token = res.json()["data"]["devResetToken"]
    assert token

    res = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "password": "NewPass123!"},
    )
    assert res.status_code == 200

    # Old password dead, new password works.
    assert client.post("/api/v1/auth/login", json={"email": "u@test.dev", "password": "Password1!"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "u@test.dev", "password": "NewPass123!"}).status_code == 200


def test_forgot_password_unknown_email_silent(client):
    res = client.post("/api/v1/auth/forgot-password", json={"email": "ghost@test.dev"})
    assert res.status_code == 200
    assert "devResetToken" not in res.json()["data"]


def test_reset_password_token_single_use(client):
    create_user("u@test.dev", "Password1!", UserRole.ANALYST)
    token = client.post("/api/v1/auth/forgot-password", json={"email": "u@test.dev"}).json()["data"]["devResetToken"]
    payload = {"token": token, "password": "NewPass123!"}
    assert client.post("/api/v1/auth/reset-password", json=payload).status_code == 200
    assert client.post("/api/v1/auth/reset-password", json=payload).status_code == 400


def test_change_password_revokes_sessions(client):
    create_user("u@test.dev", "Password1!", UserRole.ANALYST)
    res = client.post("/api/v1/auth/login", json={"email": "u@test.dev", "password": "Password1!"})
    token = res.json()["data"]["accessToken"]

    res = client.post(
        "/api/v1/auth/change-password",
        json={"currentPassword": "Password1!", "newPassword": "Changed123!"},
        headers=auth(token),
    )
    assert res.status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": "u@test.dev", "password": "Changed123!"}).status_code == 200


def test_change_password_wrong_current(client):
    create_user("u@test.dev", "Password1!", UserRole.ANALYST)
    res = client.post("/api/v1/auth/login", json={"email": "u@test.dev", "password": "Password1!"})
    token = res.json()["data"]["accessToken"]
    res = client.post(
        "/api/v1/auth/change-password",
        json={"currentPassword": "nope-nope", "newPassword": "Changed123!"},
        headers=auth(token),
    )
    assert res.status_code == 400


def test_logout_revokes_refresh(client):
    create_user("u@test.dev", "Password1!", UserRole.ANALYST)
    res = client.post("/api/v1/auth/login", json={"email": "u@test.dev", "password": "Password1!"})
    token = res.json()["data"]["accessToken"]
    refresh_cookie = res.cookies.get("bi_refresh")

    assert client.post("/api/v1/auth/logout", headers=auth(token)).status_code == 200
    res = client.post("/api/v1/auth/refresh", cookies={"bi_refresh": refresh_cookie})
    assert res.status_code == 401
