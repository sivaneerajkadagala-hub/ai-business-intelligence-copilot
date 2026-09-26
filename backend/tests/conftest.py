import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///./test.db"
os.environ["ENVIRONMENT"] = "test"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, engine, get_db
from app.core.security import hash_password
from app.main import app
from app.models.user import User, UserRole

# Recreate the schema so model changes (new tables/columns) are always
# reflected — tests truncate all rows before each case anyway.
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


def create_user(email: str, password: str, role: UserRole, full_name: str = "T") -> User:
    db = TestingSessionLocal()
    try:
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


@pytest.fixture()
def client():
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def admin_client(client):
    create_user("admin@test.dev", "Admin1234!", UserRole.ADMIN)
    res = client.post("/api/v1/auth/login", json={"email": "admin@test.dev", "password": "Admin1234!"})
    token = res.json()["data"]["accessToken"]
    return client, token


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
