import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, from_attributes=True
    )


class UserOut(CamelModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: str
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class UserCreateIn(CamelModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    role: str = Field(default="viewer", pattern="^(admin|analyst|viewer)$")


class UserUpdateIn(CamelModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    role: str | None = Field(default=None, pattern="^(admin|analyst|viewer)$")
    is_active: bool | None = None


class RoleUpdateIn(CamelModel):
    role: str = Field(pattern="^(admin|analyst|viewer)$")
