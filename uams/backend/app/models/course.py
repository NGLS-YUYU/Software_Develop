"""课程与培养方案（DATABASE.md §6）。"""

from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import BIGINT, TINYINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.organization import College, Major

_KW = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


class CourseType:
    REQUIRED = "REQUIRED"                  # 专业必修
    ELECTIVE = "ELECTIVE"                  # 专业选修
    PUBLIC_REQUIRED = "PUBLIC_REQUIRED"    # 公共必修
    PUBLIC_ELECTIVE = "PUBLIC_ELECTIVE"    # 公共选修
    PRACTICE = "PRACTICE"                  # 实践
    ALL = (REQUIRED, ELECTIVE, PUBLIC_REQUIRED, PUBLIC_ELECTIVE, PRACTICE)


class Course(Base, IdMixin, TimestampMixin):
    __tablename__ = "courses"
    __table_args__ = (
        CheckConstraint(
            "course_type IN ('REQUIRED','ELECTIVE','PUBLIC_REQUIRED',"
            "'PUBLIC_ELECTIVE','PRACTICE')",
            name="ck_courses_type",
        ),
        CheckConstraint("exam_type IN ('EXAM','CHECK')", name="ck_courses_exam_type"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_courses_status"),
        CheckConstraint("credits > 0", name="ck_courses_credits"),
        # 权重之和恒为 1，避免总评计算出现无意义结果（CLAUDE.md §21）
        CheckConstraint(
            "regular_weight + final_weight = 1.00", name="ck_courses_weight"
        ),
        Index("idx_courses_college_type", "college_id", "course_type"),
        {**_KW, "comment": "课程"},
    )

    code: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    college_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("colleges.id", ondelete="RESTRICT", name="fk_courses_college"),
        nullable=False, comment="开课学院",
    )
    course_type: Mapped[str] = mapped_column(String(20), nullable=False)
    credits: Mapped[float] = mapped_column(Numeric(4, 1), nullable=False, comment="学分")
    total_hours: Mapped[int] = mapped_column(SmallInteger, nullable=False, comment="总学时")
    theory_hours: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )
    practice_hours: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )
    exam_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="EXAM", server_default="EXAM",
        comment="EXAM 考试 / CHECK 考查",
    )
    regular_weight: Mapped[float] = mapped_column(
        Numeric(3, 2), nullable=False, default=0.40, server_default="0.40",
        comment="平时成绩权重",
    )
    final_weight: Mapped[float] = mapped_column(
        Numeric(3, 2), nullable=False, default=0.60, server_default="0.60",
        comment="期末成绩权重",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )

    college: Mapped["College"] = relationship()

    def __repr__(self) -> str:
        return f"<Course {self.code} {self.name}>"


class CoursePrerequisite(Base, IdMixin, TimestampMixin):
    """先修课程关系。

    CHECK 只能挡住直接自引用；环路（A→B→A）必须由 Service 层做图检测。
    """

    __tablename__ = "course_prerequisites"
    __table_args__ = (
        UniqueConstraint("course_id", "prerequisite_course_id", name="uk_course_prereq"),
        CheckConstraint(
            "course_id <> prerequisite_course_id", name="ck_course_prereq_self"
        ),
        {**_KW, "comment": "先修课程关系"},
    )

    course_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("courses.id", ondelete="CASCADE", name="fk_prereq_course"),
        nullable=False,
    )
    prerequisite_course_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("courses.id", ondelete="CASCADE", name="fk_prereq_prereq"),
        nullable=False,
    )
    min_score: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=60, server_default="60.00",
        comment="先修课最低成绩要求",
    )


class CurriculumPlan(Base, IdMixin, TimestampMixin):
    __tablename__ = "curriculum_plans"
    __table_args__ = (
        UniqueConstraint("major_id", "grade_year", name="uk_curriculum_major_year"),
        CheckConstraint(
            "status IN ('DRAFT','PUBLISHED','ARCHIVED')", name="ck_curriculum_status"
        ),
        {**_KW, "comment": "培养方案"},
    )

    code: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    major_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("majors.id", ondelete="RESTRICT", name="fk_curriculum_major"),
        nullable=False,
    )
    grade_year: Mapped[int] = mapped_column(SmallInteger, nullable=False, comment="适用年级")
    total_credits_required: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False)
    required_credits: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False)
    elective_credits: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", server_default="DRAFT"
    )

    major: Mapped["Major"] = relationship()
    courses: Mapped[list["CurriculumCourse"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )


class CurriculumCourse(Base, IdMixin, TimestampMixin):
    __tablename__ = "curriculum_courses"
    __table_args__ = (
        UniqueConstraint("plan_id", "course_id", name="uk_curriculum_courses"),
        Index("idx_curriculum_courses_sem", "plan_id", "suggested_semester"),
        {**_KW, "comment": "培养方案课程"},
    )

    plan_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("curriculum_plans.id", ondelete="CASCADE", name="fk_cc_plan"),
        nullable=False,
    )
    course_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("courses.id", ondelete="RESTRICT", name="fk_cc_course"),
        nullable=False,
    )
    suggested_semester: Mapped[int] = mapped_column(
        TINYINT(unsigned=True), nullable=False, comment="建议修读学期 1~8"
    )
    is_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )

    plan: Mapped["CurriculumPlan"] = relationship(back_populates="courses")
    course: Mapped["Course"] = relationship()
