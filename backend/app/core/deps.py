import uuid
from collections.abc import Callable

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AppError
from app.core.security import decode_access_token
from app.models.user import User, UserRole

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise AppError("Authentication required", "UNAUTHORIZED", 401)
    try:
        payload = decode_access_token(creds.credentials)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise AppError("Invalid or expired token", "UNAUTHORIZED", 401) from None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AppError("Account not found or inactive", "UNAUTHORIZED", 401)
    return user


def require_role(*roles: UserRole) -> Callable:
    """Endpoint guard: current user must hold one of the given roles."""

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise AppError("Insufficient permissions", "FORBIDDEN", 403)
        return user

    return checker


require_admin = require_role(UserRole.ADMIN)
require_analyst = require_role(UserRole.ADMIN, UserRole.ANALYST)
