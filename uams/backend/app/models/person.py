"""人员档案：学生、教师（DATABASE.md §5）。"""

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Numeric, SmallInteger, String
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.organization import Class, College, Major
    from app.models.user import User

_KW = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


class AcademicStatus:
    ENROLLED = "ENROLLED"      # 在读
    SUSPENDED = "SUSPENDED"    # 休学
    GRADUATED = "GRADUATED"    # 毕业
    WITHDRAWN = "WITHDRAWN"    # 退学
    ALL = (ENROLLED, SUSPENDED, GRADUATED, WITHDRAWN)


class Student(Base, IdMixin, TimestampMixin):
    __tablename__ = "students"
    __table_args__ = (
        CheckConstraint(
            "academic_status IN ('ENROLLED','SUSPENDED','GRADUATED','WITHDRAWN')",
            name="ck_students_status",
        ),
        CheckConstraint(
            "gender IN ('MALE','FEMALE','UNKNOWN')", name="ck_students_gender"
        ),
        Index("idx_students_class", "class_id"),
        Index("idx_students_major", "major_id"),
        Index("idx_students_college_year", "college_id", "enrollment_year"),
        {**_KW, "comment": "学生档案"},
    )

    user_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_students_user"),
        nullable=False, unique=True,
    )
    student_no: Mapped[str] = mapped_column(
        String(30), nullable=False, unique=True, comment="学号"
    )
    class_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("classes.id", ondelete="RESTRICT", name="fk_students_class"),
        nullable=False,
    )
    # major_id / college_id 为有意冗余，见 DATABASE.md §5.1 与 §13.3
    major_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("majors.id", ondelete="RESTRICT", name="fk_students_major"),
        nullable=False,
    )
    college_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("colleges.id", ondelete="RESTRICT", name="fk_students_college"),
        nullable=False,
    )
    gender: Mapped[str] = mapped_column(
        String(10), nullable=False, default="UNKNOWN", server_default="UNKNOWN"
    )
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    enrollment_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    academic_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AcademicStatus.ENROLLED,
        server_default=AcademicStatus.ENROLLED,
    )
    total_credits: Mapped[float] = mapped_column(
        Numeric(5, 1), nullable=False, default=0, server_default="0.0",
        comment="已修总学分",
    )
    gpa: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True, comment="平均绩点")

    user: Mapped["User"] = relationship()
    klass: Mapped["Class"] = relationship()
    major: Mapped["Major"] = relationship()
    college: Mapped["College"] = relationship()

    def __repr__(self) -> str:
        return f"<Student {self.student_no}>"


class Teacher(Base, IdMixin, TimestampMixin):
    __tablename__ = "teachers"
    __table_args__ = (
        CheckConstraint(
            "title IS NULL OR title IN "
            "('ASSISTANT','LECTURER','ASSOCIATE_PROFESSOR','PROFESSOR')",
            name="ck_teachers_title",
        ),
        CheckConstraint(
            "status IN ('ACTIVE','LEAVE','RETIRED')", name="ck_teachers_status"
        ),
        Index("idx_teachers_college", "college_id"),
        {**_KW, "comment": "教师档案"},
    )

    user_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_teachers_user"),
        nullable=False, unique=True,
    )
    teacher_no: Mapped[str] = mapped_column(
        String(30), nullable=False, unique=True, comment="工号"
    )
    college_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("colleges.id", ondelete="RESTRICT", name="fk_teachers_college"),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="职称")
    gender: Mapped[str] = mapped_column(
        String(10), nullable=False, default="UNKNOWN", server_default="UNKNOWN"
    )
    hire_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )

    user: Mapped["User"] = relationship()
    college: Mapped["College"] = relationship()

    def __repr__(self) -> str:
        return f"<Teacher {self.teacher_no}>"
