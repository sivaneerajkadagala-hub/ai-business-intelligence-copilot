import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    refresh_token_expiry,
    utcnow,
    verify_password,
)
from app.models.token import PasswordResetToken, RefreshToken
from app.models.user import User, UserRole
from app.services.audit import audit

RESET_TOKEN_TTL = timedelta(hours=1)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _issue_refresh_token(
    db: Session,
    user: User,
    *,
    family_id: uuid.UUID | None,
    ip: str | None,
    user_agent: str | None,
) -> str:
    token = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(token),
            family_id=family_id or uuid.uuid4(),
            expires_at=refresh_token_expiry(),
            user_agent=user_agent,
            ip=ip,
        )
    )
    return token


def issue_session(
    db: Session, user: User, *, ip: str | None, user_agent: str | None
) -> tuple[str, str]:
    """Create a fresh access + refresh pair. Returns (access, refresh)."""
    access = create_access_token(user.id, user.role.value)
    refresh = _issue_refresh_token(db, user, family_id=None, ip=ip, user_agent=user_agent)
    return access, refresh


def register(
    db: Session, *, email: str, password: str, full_name: str, ip: str | None
) -> User:
    email = _normalize_email(email)
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        raise AppError("An account with this email already exists", "CONFLICT", 409)

    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name.strip(),
        role=UserRole.ANALYST,  # self-registered accounts start as analysts
        is_active=True,
    )
    db.add(user)
    db.flush()
    audit(
        db,
        user_id=user.id,
        action="auth.register",
        resource_type="user",
        resource_id=str(user.id),
        ip=ip,
    )
    db.commit()
    db.refresh(user)
    return user


def login(
    db: Session, *, email: str, password: str, ip: str | None, user_agent: str | None
) -> tuple[User, str, str]:
    user = db.scalar(select(User).where(User.email == _normalize_email(email)))
    if user is None or not verify_password(password, user.password_hash):
        audit(
            db,
            user_id=user.id if user else None,
            action="auth.login_failed",
            resource_type="user",
            resource_id=str(user.id) if user else None,
            ip=ip,
        )
        db.commit()
        raise AppError("Invalid email or password", "UNAUTHORIZED", 401)
    if not user.is_active:
        raise AppError("This account has been deactivated", "FORBIDDEN", 403)

    user.last_login_at = utcnow()
    access, refresh = issue_session(db, user, ip=ip, user_agent=user_agent)
    audit(
        db,
        user_id=user.id,
        action="auth.login",
        resource_type="user",
        resource_id=str(user.id),
        ip=ip,
    )
    db.commit()
    return user, access, refresh


def refresh_session(
    db: Session, *, refresh_token: str | None, ip: str | None, user_agent: str | None
) -> tuple[User, str, str]:
    if not refresh_token:
        raise AppError("No refresh token", "UNAUTHORIZED", 401)

    record = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh_token))
    )
    if record is None:
        raise AppError("Invalid refresh token", "UNAUTHORIZED", 401)

    if record.revoked_at is not None:
        # Reuse of a rotated token — likely theft. Nuke the whole family.
        db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == record.family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=utcnow())
        )
        audit(
            db,
            user_id=record.user_id,
            action="auth.refresh_reuse_detected",
            resource_type="user",
            resource_id=str(record.user_id),
            ip=ip,
        )
        db.commit()
        raise AppError("Session expired — please sign in again", "UNAUTHORIZED", 401)

    if record.expires_at.replace(tzinfo=record.expires_at.tzinfo or utcnow().tzinfo) < utcnow():
        raise AppError("Refresh token expired", "UNAUTHORIZED", 401)

    user = db.get(User, record.user_id)
    if user is None or not user.is_active:
        raise AppError("Account not found or inactive", "UNAUTHORIZED", 401)

    # Rotate: revoke presented token, issue successor in the same family.
    record.revoked_at = utcnow()
    access = create_access_token(user.id, user.role.value)
    new_refresh = _issue_refresh_token(
        db, user, family_id=record.family_id, ip=ip, user_agent=user_agent
    )
    db.flush()
    db.commit()
    return user, access, new_refresh


def logout(db: Session, *, refresh_token: str | None, user: User) -> None:
    if refresh_token:
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == hash_token(refresh_token))
            .values(revoked_at=utcnow())
        )
    audit(db, user_id=user.id, action="auth.logout", resource_type="user", resource_id=str(user.id))
    db.commit()


def forgot_password(db: Session, *, email: str, ip: str | None) -> str | None:
    """Create a reset token if the account exists. Returns the raw token —
    in production this is emailed; in demo mode the caller surfaces it."""
    user = db.scalar(select(User).where(User.email == _normalize_email(email)))
    if user is None:
        return None  # never reveal whether the account exists

    token = generate_refresh_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=utcnow() + RESET_TOKEN_TTL,
        )
    )
    audit(
        db,
        user_id=user.id,
        action="auth.forgot_password",
        resource_type="user",
        resource_id=str(user.id),
        ip=ip,
    )
    db.commit()
    return token


def reset_password(db: Session, *, token: str, new_password: str, ip: str | None) -> None:
    record = db.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == hash_token(token)
        )
    )
    if (
        record is None
        or record.used_at is not None
        or record.expires_at.replace(tzinfo=record.expires_at.tzinfo or utcnow().tzinfo) < utcnow()
    ):
        raise AppError("Reset link is invalid or has expired", "BAD_REQUEST", 400)

    user = db.get(User, record.user_id)
    if user is None:
        raise AppError("Reset link is invalid or has expired", "BAD_REQUEST", 400)

    user.password_hash = hash_password(new_password)
    record.used_at = utcnow()
    # Invalidate all existing sessions.
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    audit(
        db,
        user_id=user.id,
        action="auth.reset_password",
        resource_type="user",
        resource_id=str(user.id),
        ip=ip,
    )
    db.commit()


def change_password(
    db: Session, *, user: User, current_password: str, new_password: str, ip: str | None
) -> None:
    if not verify_password(current_password, user.password_hash):
        raise AppError("Current password is incorrect", "BAD_REQUEST", 400)
    user.password_hash = hash_password(new_password)
    # Invalidate every session except the one used to make this change —
    # simplest correct behavior: revoke all, client re-authenticates.
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    audit(
        db,
        user_id=user.id,
        action="auth.change_password",
        resource_type="user",
        resource_id=str(user.id),
        ip=ip,
    )
    db.commit()
