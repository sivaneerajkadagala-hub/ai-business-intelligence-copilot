import math
import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_admin
from app.core.errors import AppError
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.schemas.common import ok
from app.schemas.user import RoleUpdateIn, UserCreateIn, UserOut, UserUpdateIn
from app.services.audit import audit

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_admin)],
)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _get_or_404(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise AppError("User not found", "NOT_FOUND", 404)
    return user


@router.get("")
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    total = db.scalar(select(func.count()).select_from(User)) or 0
    rows = db.scalars(
        select(User).order_by(User.created_at).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return ok(
        {
            "items": [UserOut.model_validate(u).model_dump(by_alias=True) for u in rows],
            "total": total,
            "page": page,
            "pages": max(1, math.ceil(total / page_size)),
        }
    )


@router.post("", status_code=201)
def create_user(
    body: UserCreateIn,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> dict:
    email = body.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise AppError("An account with this email already exists", "CONFLICT", 409)

    user = User(
        email=email,
        password_hash=hash_password(body.password),
        full_name=body.full_name.strip(),
        role=UserRole(body.role),
        is_active=True,
    )
    db.add(user)
    db.flush()
    audit(
        db,
        user_id=actor.id,
        action="users.create",
        resource_type="user",
        resource_id=str(user.id),
        meta={"email": user.email, "role": user.role.value},
        ip=_client_ip(request),
    )
    db.commit()
    db.refresh(user)
    return ok(UserOut.model_validate(user).model_dump(by_alias=True))


@router.get("/{user_id}")
def get_user(user_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    return ok(UserOut.model_validate(_get_or_404(db, user_id)).model_dump(by_alias=True))


@router.patch("/{user_id}")
def update_user(
    user_id: uuid.UUID,
    body: UserUpdateIn,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> dict:
    user = _get_or_404(db, user_id)
    if user_id == actor.id and body.is_active is False:
        raise AppError("You cannot deactivate your own account", "BAD_REQUEST", 400)

    changes = body.model_dump(exclude_unset=True)
    if "full_name" in changes:
        user.full_name = changes["full_name"].strip()
    if "role" in changes:
        if user_id == actor.id and changes["role"] != "admin":
            raise AppError("You cannot remove your own admin role", "BAD_REQUEST", 400)
        user.role = UserRole(changes["role"])
    if "is_active" in changes:
        user.is_active = changes["is_active"]

    audit(
        db,
        user_id=actor.id,
        action="users.update",
        resource_type="user",
        resource_id=str(user.id),
        meta=changes,
        ip=_client_ip(request),
    )
    db.commit()
    db.refresh(user)
    return ok(UserOut.model_validate(user).model_dump(by_alias=True))


@router.patch("/{user_id}/role")
def update_role(
    user_id: uuid.UUID,
    body: RoleUpdateIn,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> dict:
    user = _get_or_404(db, user_id)
    if user_id == actor.id and body.role != "admin":
        raise AppError("You cannot remove your own admin role", "BAD_REQUEST", 400)
    user.role = UserRole(body.role)
    audit(
        db,
        user_id=actor.id,
        action="users.update_role",
        resource_type="user",
        resource_id=str(user.id),
        meta={"role": body.role},
        ip=_client_ip(request),
    )
    db.commit()
    db.refresh(user)
    return ok(UserOut.model_validate(user).model_dump(by_alias=True))


@router.delete("/{user_id}")
def delete_user(
    user_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> dict:
    """Soft-delete: deactivates the account (owned resources stay referencable)."""
    user = _get_or_404(db, user_id)
    if user_id == actor.id:
        raise AppError("You cannot deactivate your own account", "BAD_REQUEST", 400)
    user.is_active = False
    audit(
        db,
        user_id=actor.id,
        action="users.deactivate",
        resource_type="user",
        resource_id=str(user.id),
        ip=_client_ip(request),
    )
    db.commit()
    return ok(message="User deactivated")
