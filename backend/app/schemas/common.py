from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    message: str | None = None
    errorCode: str | None = None


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    pages: int


def ok(data: T | None = None, message: str | None = None) -> dict:
    return {"success": True, "data": data, "message": message, "errorCode": None}
