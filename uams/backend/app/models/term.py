"""学期（AcademicTerm，TASK-011）。

Course 是课程定义；AcademicTerm 是时间维度；TeachingClass 是某学期某课程的一次开课。

关系：
    AcademicTerm 1 ─── N TeachingClass
"""

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.teaching import TeachingClass

_KW = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


class TermStatus:
    PLANNED = "PLANNED"    # 已创建，尚未开始
    ACTIVE = "ACTIVE"      # 当前教学学期
    ENDED = "ENDED"        # 已结束
    ALL = (PLANNED, ACTIVE, ENDED)


class AcademicTerm(Base, IdMixin, TimestampMixin):
    __tablename__ = "academic_terms"
    __table_args__ = (
        # 同一学年 + 学期序号唯一（如 2026-2027 + 1 只能存在一个）
        UniqueConstraint("academic_year", "semester", name="uk_terms_year_sem"),
        CheckConstraint("semester IN (1,2)", name="ck_terms_semester"),
        CheckConstraint(
            "status IN ('PLANNED','ACTIVE','ENDED')", name="ck_terms_status"
        ),
        CheckConstraint("end_date > start_date", name="ck_terms_dates"),
        Index("idx_terms_status", "status"),
        {**_KW, "comment": "学期"},
    )

    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="学期名称")
    academic_year: Mapped[str] = mapped_column(
        String(9), nullable=False, comment="学年，如 2026-2027"
    )
    semester: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, comment="学期序号：1 或 2"
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False, comment="开始日期")
    end_date: Mapped[date] = mapped_column(Date, nullable=False, comment="结束日期")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TermStatus.PLANNED,
        server_default=TermStatus.PLANNED,
    )

    teaching_classes: Mapped[list["TeachingClass"]] = relationship(
        back_populates="term"
    )

    def __repr__(self) -> str:
        return f"<AcademicTerm {self.name}>"
