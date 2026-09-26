from pydantic import EmailStr, Field

from app.schemas.user import CamelModel


class RegisterIn(CamelModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)


class LoginIn(CamelModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ForgotPasswordIn(CamelModel):
    email: EmailStr


class ResetPasswordIn(CamelModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=8, max_length=128)


class ChangePasswordIn(CamelModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class ProfileUpdateIn(CamelModel):
    full_name: str = Field(min_length=1, max_length=200)
