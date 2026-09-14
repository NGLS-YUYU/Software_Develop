"""通用 Repository 基类。

避免每个模块重复 CRUD 样板（CLAUDE.md §11：Repository 只负责数据库访问）。
"""

from typing import Any, Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, db: Session):
        self.db = db

    # --- 查询 ---

    def get(self, obj_id: int) -> ModelT | None:
        return self.db.get(self.model, obj_id)

    def get_by(self, **filters: Any) -> ModelT | None:
        stmt = select(self.model).filter_by(**filters)
        return self.db.execute(stmt).scalar_one_or_none()

    def exists(self, **filters: Any) -> bool:
        stmt = select(func.count()).select_from(self.model).filter_by(**filters)
        return (self.db.execute(stmt).scalar() or 0) > 0

    def list_all(self, **filters: Any) -> list[ModelT]:
        stmt = select(self.model)
        if filters:
            stmt = stmt.filter_by(**filters)
        return list(self.db.execute(stmt).scalars())

    def paginate(
        self,
        stmt: Select,
        offset: int,
        limit: int,
    ) -> tuple[list[ModelT], int]:
        """对给定语句分页，返回 (当前页数据, 总数)。"""
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = self.db.execute(count_stmt).scalar() or 0
        rows = list(self.db.execute(stmt.offset(offset).limit(limit)).scalars())
        return rows, total

    # --- 写入 ---

    def create(self, **kwargs: Any) -> ModelT:
        obj = self.model(**kwargs)
        self.db.add(obj)
        self.db.flush()
        return obj

    def add(self, obj: ModelT) -> ModelT:
        self.db.add(obj)
        self.db.flush()
        return obj

    def update(self, obj: ModelT, data: dict[str, Any]) -> ModelT:
        for k, v in data.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        self.db.flush()
        return obj

    def delete(self, obj: ModelT) -> None:
        self.db.delete(obj)
        self.db.flush()
