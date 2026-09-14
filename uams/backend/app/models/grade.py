"""成绩（DATABASE.md §9）。"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
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


class GradeStatus:
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ALL = (DRAFT, SUBMITTED, APPROVED, REJECTED)


# 绩点换算表（DATABASE.md §9.3），按分数段降序匹配
GRADE_POINT_TABLE: list[tuple[Decimal, Decimal]] = [
    (Decimal("90"), Decimal("4.0")),
    (Decimal("85"), Decimal("3.7")),
    (Decimal("80"), Decimal("3.3")),
    (Decimal("75"), Decimal("3.0")),
    (Decimal("70"), Decimal("2.7")),
    (Decimal("65"), Decimal("2.3")),
    (Decimal("60"), Decimal("1.0")),
]
PASS_SCORE = Decimal("60")


def score_to_point(score: Decimal | float | None) -> Decimal | None:
    if score is None:
        return None
    s = Decimal(str(score))
    for threshold, point in GRADE_POINT_TABLE:
        if s >= threshold:
            return point
    return Decimal("0.0")


class Grade(Base, IdMixin, TimestampMixin):
    __tablename__ = "grades"
    __table_args__ = (
        UniqueConstraint("student_id", "teaching_class_id", name="uk_grades"),
        CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','APPROVED','REJECTED')",
            name="ck_grades_status",
        ),
        CheckConstraint(
            "regular_score IS NULL OR regular_score BETWEEN 0 AND 100",
            name="ck_grades_regular",
        ),
        CheckConstraint(
            "final_score IS NULL OR final_score BETWEEN 0 AND 100",
            name="ck_grades_final",
        ),
        CheckConstraint(
            "total_score IS NULL OR total_score BETWEEN 0 AND 100",
            name="ck_grades_total",
        ),
        Index("idx_grades_student_sem", "student_id", "semester"),
        Index("idx_grades_tc_status", "teaching_class_id", "status"),
        {**_KW, "comment": "成绩"},
    )

    student_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("students.id", ondelete="CASCADE", name="fk_grades_student"),
        nullable=False,
    )
    teaching_class_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("teaching_classes.id", ondelete="CASCADE", name="fk_grades_tc"),
        nullable=False,
    )
    course_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("courses.id", ondelete="RESTRICT", name="fk_grades_course"),
        nullable=False,
    )
    semester: Mapped[str] = mapped_column(String(16), nullable=False)

    regular_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True, comment="平时成绩"
    )
    final_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True, comment="期末成绩"
    )
    total_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True, comment="总评，由后端按课程权重计算"
    )
    grade_point: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    # 学分快照：课程学分日后调整不应改变历史成绩（DATABASE.md §9.1）
    credits: Mapped[Decimal] = mapped_column(
        Numeric(4, 1), nullable=False, comment="学分快照"
    )
    is_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=GradeStatus.DRAFT,
        server_default=GradeStatus.DRAFT,
    )
    submitted_by: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("teachers.id", ondelete="SET NULL", name="fk_grades_submitter"),
        nullable=True,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_grades_approver"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    student: Mapped["Student"] = relationship()
    teaching_class: Mapped["TeachingClass"] = relationship()
    course: Mapped["Course"] = relationship()

    def compute(self, regular_weight: Decimal, final_weight: Decimal) -> None:
        """按课程权重计算总评、绩点与及格标记（CLAUDE.md §21）。"""
        if self.regular_score is None or self.final_score is None:
            self.total_score = None
            self.grade_point = None
            self.is_passed = None
            return
        total = (
            Decimal(str(self.regular_score)) * Decimal(str(regular_weight))
            + Decimal(str(self.final_score)) * Decimal(str(final_weight))
        ).quantize(Decimal("0.01"))
        self.total_score = total
        self.grade_point = score_to_point(total)
        self.is_passed = total >= PASS_SCORE
