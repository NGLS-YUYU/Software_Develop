"""选课（DATABASE.md §8）。"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.course import Course
    from app.models.person import Student
    from app.models.teaching import TeachingClass

_KW = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


class SelectionState:
    SELECTED = "SELECTED"
    DROPPED = "DROPPED"


class CourseSelection(Base, IdMixin, TimestampMixin):
    __tablename__ = "course_selections"
    __table_args__ = (
        # 防重复选课的最后一道防线：并发下应用层判断可能失效（PRD §15）
        UniqueConstraint("student_id", "teaching_class_id", name="uk_selection"),
        CheckConstraint("status IN ('SELECTED','DROPPED')", name="ck_selection_status"),
        Index("idx_selection_student_sem", "student_id", "semester"),
        Index("idx_selection_tc", "teaching_class_id", "status"),
        {**_KW, "comment": "选课记录"},
    )

    student_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("students.id", ondelete="CASCADE", name="fk_sel_student"),
        nullable=False,
    )
    teaching_class_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("teaching_classes.id", ondelete="CASCADE", name="fk_sel_tc"),
        nullable=False,
    )
    course_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("courses.id", ondelete="RESTRICT", name="fk_sel_course"),
        nullable=False,
    )
    semester: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SelectionState.SELECTED,
        server_default=SelectionState.SELECTED,
    )
    selected_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    dropped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    student: Mapped["Student"] = relationship()
    teaching_class: Mapped["TeachingClass"] = relationship()
    course: Mapped["Course"] = relationship()


class SelectionPeriod(Base, IdMixin, TimestampMixin):
    """选课时间窗口。"""

    __tablename__ = "selection_periods"
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="ck_sel_period_time"),
        CheckConstraint(
            "status IN ('PENDING','ACTIVE','CLOSED')", name="ck_sel_period_status"
        ),
        Index("idx_selection_period", "semester", "status"),
        {**_KW, "comment": "选课时间窗口"},
    )

    semester: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    target_grade_year: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="限定年级，NULL 为全部"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING", server_default="PENDING"
    )

    def is_open_now(self, grade_year: int | None = None) -> bool:
        now = datetime.now()
        if self.status != "ACTIVE" or not (self.start_time <= now <= self.end_time):
            return False
        if self.target_grade_year is not None and grade_year is not None:
            return self.target_grade_year == grade_year
        return True
