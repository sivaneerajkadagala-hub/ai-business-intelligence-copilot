from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.errors import AppError
from app.schemas.auth import (
    ChangePasswordIn,
    ForgotPasswordIn,
    LoginIn,
    ProfileUpdateIn,
    RegisterIn,
    ResetPasswordIn,
)
from app.schemas.common import ok
from app.schemas.user import UserOut
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

REFRESH_COOKIE = "bi_refresh"


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.ENVIRONMENT == "production",
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")


def _auth_payload(user, access_token: str) -> dict:
    return {"accessToken": access_token, "user": UserOut.model_validate(user).model_dump(by_alias=True)}


@router.post("/register", status_code=201)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)) -> dict:
    user = auth_service.register(
        db,
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        ip=_client_ip(request),
    )
    return ok({"user": UserOut.model_validate(user).model_dump(by_alias=True)})


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    user, access, refresh = auth_service.login(
        db,
        email=body.email,
        password=body.password,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    _set_refresh_cookie(response, refresh)
    return ok(_auth_payload(user, access))


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    auth_service.logout(db, refresh_token=request.cookies.get(REFRESH_COOKIE), user=user)
    _clear_refresh_cookie(response)
    return ok(message="Signed out")


@router.post("/refresh")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    user, access, new_refresh = auth_service.refresh_session(
        db,
        refresh_token=request.cookies.get(REFRESH_COOKIE),
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    _set_refresh_cookie(response, new_refresh)
    return ok(_auth_payload(user, access))


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordIn, request: Request, db: Session = Depends(get_db)) -> dict:
    token = auth_service.forgot_password(db, email=body.email, ip=_client_ip(request))
    data: dict = {}
    # Demo convenience: no SMTP in dev. In production the token is emailed only.
    if token and settings.ENVIRONMENT != "production":
        data["devResetToken"] = token
    return ok(data, message="If that account exists, a reset link has been sent")


@router.post("/reset-password")
def reset_password(body: ResetPasswordIn, request: Request, db: Session = Depends(get_db)) -> dict:
    auth_service.reset_password(
        db, token=body.token, new_password=body.password, ip=_client_ip(request)
    )
    return ok(message="Password has been reset — please sign in")


@router.post("/change-password")
def change_password(
    body: ChangePasswordIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    auth_service.change_password(
        db,
        user=user,
        current_password=body.current_password,
        new_password=body.new_password,
        ip=_client_ip(request),
    )
    _clear_refresh_cookie(response)
    return ok(message="Password changed — please sign in again")


@router.get("/me")
def me(user=Depends(get_current_user)) -> dict:
    return ok(UserOut.model_validate(user).model_dump(by_alias=True))


@router.patch("/me")
def update_me(
    body: ProfileUpdateIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    user.full_name = body.full_name.strip()
    db.commit()
    db.refresh(user)
    return ok(UserOut.model_validate(user).model_dump(by_alias=True))
