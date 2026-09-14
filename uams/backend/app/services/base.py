"""通用 CRUD Service 基类。

提供「建/改/删 + 唯一性校验 + 引用保护」的公共实现，
各模块只需声明差异部分（CLAUDE.md §11：业务逻辑集中在 Service）。
"""

from typing import Any, Generic, TypeVar

from sqlalchemy import Select, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, NotFound
from app.db.base import Base
from app.schemas.common import PageParams

ModelT = TypeVar("ModelT", bound=Base)


class BaseCrudService(Generic[ModelT]):
    model: type[ModelT]
    # 关键词模糊搜索作用的字段
    search_fields: tuple[str, ...] = ()
    # 需要保证唯一的字段（如 code）
    unique_fields: tuple[str, ...] = ()
    # 默认排序字段
    default_order: str = "id"
    entity_name: str = "记录"

    def __init__(self, db: Session):
        self.db = db

    # --- 查询 ---

    def base_stmt(self) -> Select:
        return select(self.model)

    def apply_filters(self, stmt: Select, **filters: Any) -> Select:
        for key, val in filters.items():
            if val is None or not hasattr(self.model, key):
                continue
            stmt = stmt.where(getattr(self.model, key) == val)
        return stmt

    def apply_search(self, stmt: Select, keyword: str | None) -> Select:
        if not keyword or not self.search_fields:
            return stmt
        like = f"%{keyword}%"
        conds = [
            getattr(self.model, f).like(like)
            for f in self.search_fields
            if hasattr(self.model, f)
        ]
        return stmt.where(or_(*conds)) if conds else stmt

    def apply_order(self, stmt: Select, params: PageParams) -> Select:
        field = params.order_by or self.default_order
        col = getattr(self.model, field, None) or getattr(self.model, self.default_order)
        return stmt.order_by(col.desc() if params.order_desc else col.asc())

    def paginate(self, params: PageParams, **filters: Any) -> tuple[list[ModelT], int]:
        from app.repositories.base import BaseRepository

        stmt = self.base_stmt()
        stmt = self.apply_filters(stmt, **filters)
        stmt = self.apply_search(stmt, params.keyword)
        stmt = self.apply_order(stmt, params)

        repo: BaseRepository = BaseRepository(self.db)
        repo.model = self.model
        return repo.paginate(stmt, params.offset, params.page_size)

    def get_or_404(self, obj_id: int) -> ModelT:
        obj = self.db.get(self.model, obj_id)
        if obj is None:
            raise NotFound(f"{self.entity_name}不存在（id={obj_id}）")
        return obj

    # --- 写入 ---

    def _check_unique(self, data: dict[str, Any], exclude_id: int | None = None) -> None:
        for field in self.unique_fields:
            val = data.get(field)
            if val is None:
                continue
            stmt = select(self.model).where(getattr(self.model, field) == val)
            if exclude_id is not None:
                stmt = stmt.where(self.model.id != exclude_id)
            if self.db.execute(stmt).first():
                raise Conflict(f"{self.entity_name}的 {field} 已存在：{val}")

    def validate_create(self, data: dict[str, Any]) -> None:
        """子类可覆写，做业务校验（如外键存在性）。"""

    def validate_update(self, obj: ModelT, data: dict[str, Any]) -> None:
        """子类可覆写。"""

    def validate_delete(self, obj: ModelT) -> None:
        """子类可覆写，做引用检查。"""

    def create(self, data: dict[str, Any]) -> ModelT:
        self._check_unique(data)
        self.validate_create(data)
        obj = self.model(**data)
        self.db.add(obj)
        self._commit()
        return obj

    def update(self, obj_id: int, data: dict[str, Any]) -> ModelT:
        obj = self.get_or_404(obj_id)
        data = {k: v for k, v in data.items() if v is not None}
        self._check_unique(data, exclude_id=obj_id)
        self.validate_update(obj, data)
        for k, v in data.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        self._commit()
        return obj

    def delete(self, obj_id: int) -> None:
        obj = self.get_or_404(obj_id)
        self.validate_delete(obj)
        self.db.delete(obj)
        self._commit()

    def _commit(self) -> None:
        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            msg = str(e.orig) if e.orig else str(e)
            if "foreign key" in msg.lower():
                raise Conflict(
                    f"操作被拒绝：{self.entity_name}存在关联数据或引用的数据不存在"
                ) from e
            if "duplicate" in msg.lower():
                raise Conflict(f"{self.entity_name}已存在重复数据") from e
            raise
