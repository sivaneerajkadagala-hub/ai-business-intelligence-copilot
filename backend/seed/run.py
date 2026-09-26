"""Seed demo accounts. Idempotent — safe to run on every container start.

Demo credentials (documented in README):
    admin@bicopilot.dev    / Demo1234!
    analyst@bicopilot.dev  / Demo1234!
    viewer@bicopilot.dev   / Demo1234!
"""

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole

DEMO_PASSWORD = "Demo1234!"

DEMO_USERS = [
    ("admin@bicopilot.dev", "Demo Admin", UserRole.ADMIN),
    ("analyst@bicopilot.dev", "Demo Analyst", UserRole.ANALYST),
    ("viewer@bicopilot.dev", "Demo Viewer", UserRole.VIEWER),
]


def seed_users() -> None:
    with SessionLocal() as db:
        created = 0
        for email, name, role in DEMO_USERS:
            if db.scalar(select(User).where(User.email == email)):
                continue
            db.add(
                User(
                    email=email,
                    password_hash=hash_password(DEMO_PASSWORD),
                    full_name=name,
                    role=role,
                    is_active=True,
                )
            )
            created += 1
        db.commit()
    print(f"seed: {created} user(s) created, {len(DEMO_USERS) - created} already existed")


if __name__ == "__main__":
    seed_users()
