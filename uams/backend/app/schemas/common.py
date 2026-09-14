"""通用 Schema：分页、响应包装。

PRD §13.1：分页、排序、搜索参数统一命名。
"""

from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field

T = TypeVar("T")


class PageParams:
    """分页查询参数依赖。"""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="页码，从 1 开始"),
        page_size: int = Query(20, ge=1, le=200, description="每页条数"),
        keyword: str | None = Query(None, max_length=100, description="搜索关键词"),
        order_by: str | None = Query(None, max_length=50, description="排序字段"),
        order_desc: bool = Query(False, description="是否降序"),
    ):
        self.page = page
        self.page_size = page_size
        self.keyword = keyword.strip() if keyword else None
        self.order_by = order_by
        self.order_desc = order_desc

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int = Field(..., description="总条数")
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def build(cls, items: list[T], total: int, params: PageParams) -> "PageResult[T]":
        pages = (total + params.page_size - 1) // params.page_size if total else 0
        return cls(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
            total_pages=pages,
        )


class IdResponse(BaseModel):
    id: int


class MessageResponse(BaseModel):
    message: str
