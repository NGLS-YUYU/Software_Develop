"""学期业务逻辑（TASK-011）。

AcademicTerm 是时间维度：同一学年 + 学期序号唯一；
全系统最多存在一个 ACTIVE（进行中）学期；
状态只允许 PLANNED → ACTIVE → ENDED 单向流转。
"""

from datetime import date
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict
from app.models.teaching import TeachingClass
from app.models.term import AcademicTerm, TermStatus
from app.services.base import BaseCrudService


class AcademicTermService(BaseCrudService[AcademicTerm]):
    model = AcademicTerm
    search_fields = ("name", "academic_year")
    unique_fields = ()
    default_order = "academic_year"
    entity_name = "学期"

    def base_stmt(self) -> Select:
        return select(AcademicTerm)

    # --- 校验 ---

    def _check_year_semester_unique(
        self, academic_year: str, semester: int, exclude_id: int | None = None
    ) -> None:
        stmt = select(AcademicTerm).where(
            AcademicTerm.academic_year == academic_year,
            AcademicTerm.semester == semester,
        )
        if exclude_id is not None:
            stmt = stmt.where(AcademicTerm.id != exclude_id)
        if self.db.execute(stmt).first():
            raise Conflict(f"该学年学期已存在：{academic_year} 第 {semester} 学期")

    @staticmethod
    def _check_dates(start_date: date, end_date: date) -> None:
        if end_date <= start_date:
            raise Conflict("结束日期必须晚于开始日期")

    def _ensure_single_active(self, exclude_id: int | None = None) -> None:
        stmt = select(AcademicTerm).where(AcademicTerm.status == TermStatus.ACTIVE)
        if exclude_id is not None:
            stmt = stmt.where(AcademicTerm.id != exclude_id)
        if self.db.execute(stmt).first():
            raise Conflict("已存在进行中的学期，不能同时激活多个学期")

    def _validate_status_transition(
        self, old: str, new: str, exclude_id: int | None = None
    ) -> None:
        if old == TermStatus.ENDED:
            raise Conflict("已结束的学期不能更改状态")
        if new == TermStatus.ACTIVE:
            self._ensure_single_active(exclude_id=exclude_id)

    def validate_create(self, data: dict[str, Any]) -> None:
        self._check_dates(data["start_date"], data["end_date"])
        self._check_year_semester_unique(data["academic_year"], data["semester"])
        if data.get("status") == TermStatus.ACTIVE:
            self._ensure_single_active()

    def validate_update(self, obj: AcademicTerm, data: dict[str, Any]) -> None:
        ay = data.get("academic_year", obj.academic_year)
        sem = data.get("semester", obj.semester)
        self._check_year_semester_unique(ay, sem, exclude_id=obj.id)

        sd = data.get("start_date", obj.start_date)
        ed = data.get("end_date", obj.end_date)
        self._check_dates(sd, ed)

        new_status = data.get("status")
        if new_status and new_status != obj.status:
            self._validate_status_transition(obj.status, new_status, exclude_id=obj.id)

    def validate_delete(self, obj: AcademicTerm) -> None:
        n = self.db.execute(
            select(func.count())
            .select_from(TeachingClass)
            .where(TeachingClass.term_id == obj.id)
        ).scalar()
        if n:
            raise Conflict(f"该学期下存在 {n} 个教学班，无法删除")

    # --- 状态动作 ---

    def activate(self, term_id: int) -> AcademicTerm:
        obj = self.get_or_404(term_id)
        if obj.status == TermStatus.ENDED:
            raise Conflict("已结束的学期不能激活")
        if obj.status != TermStatus.ACTIVE:
            self._ensure_single_active(exclude_id=term_id)
            obj.status = TermStatus.ACTIVE
            self._commit()
        return obj

    def end(self, term_id: int) -> AcademicTerm:
        obj = self.get_or_404(term_id)
        if obj.status != TermStatus.ACTIVE:
            raise Conflict("只有进行中的学期才能结束")
        obj.status = TermStatus.ENDED
        self._commit()
        return obj

    # --- 辅助查询 ---

    def teaching_class_count(self, term_id: int) -> int:
        return (
            self.db.execute(
                select(func.count())
                .select_from(TeachingClass)
                .where(TeachingClass.term_id == term_id)
            ).scalar()
            or 0
        )
