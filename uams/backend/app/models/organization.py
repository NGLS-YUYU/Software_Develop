"""组织结构：学院、专业、班级、教室（DATABASE.md §4）。"""

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, SmallInteger, String
from sqlalchemy.dialects.mysql import BIGINT, TINYINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.person import Teacher

_KW = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}

ACTIVE_STATUS = ("ACTIVE", "INACTIVE")


class College(Base, IdMixin, TimestampMixin):
    __tablename__ = "colleges"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_colleges_status"),
        {**_KW, "comment": "学院"},
    )

    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, comment="学院代码")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="学院名称")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )

    majors: Mapped[list["Major"]] = relationship(back_populates="college")

    def __repr__(self) -> str:
        return f"<College {self.code} {self.name}>"


class Major(Base, IdMixin, TimestampMixin):
    __tablename__ = "majors"
    __table_args__ = (
        CheckConstraint(
            "degree_type IN ('BACHELOR','MASTER','DOCTOR')", name="ck_majors_degree"
        ),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_majors_status"),
        Index("idx_majors_college", "college_id"),
        {**_KW, "comment": "专业"},
    )

    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    college_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("colleges.id", ondelete="RESTRICT", name="fk_majors_college"),
        nullable=False,
    )
    degree_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="BACHELOR", server_default="BACHELOR"
    )
    duration_years: Mapped[int] = mapped_column(
        TINYINT(unsigned=True), nullable=False, default=4, server_default="4"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )

    college: Mapped["College"] = relationship(back_populates="majors")
    classes: Mapped[list["Class"]] = relationship(back_populates="major")

    def __repr__(self) -> str:
        return f"<Major {self.code} {self.name}>"


class Class(Base, IdMixin, TimestampMixin):
    __tablename__ = "classes"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_classes_status"),
        Index("idx_classes_major_grade", "major_id", "grade_year"),
        {**_KW, "comment": "行政班级"},
    )

    code: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    major_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("majors.id", ondelete="RESTRICT", name="fk_classes_major"),
        nullable=False,
    )
    grade_year: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, comment="入学年份"
    )
    counselor_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("teachers.id", ondelete="SET NULL", name="fk_classes_counselor"),
        nullable=True,
        comment="辅导员",
    )
    student_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0",
        comment="冗余计数，学籍变更时同步",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )

    major: Mapped["Major"] = relationship(back_populates="classes")
    counselor: Mapped["Teacher | None"] = relationship(foreign_keys=[counselor_id])

    def __repr__(self) -> str:
        return f"<Class {self.code} {self.name}>"


class Classroom(Base, IdMixin, TimestampMixin):
    __tablename__ = "classrooms"
    __table_args__ = (
        CheckConstraint(
            "room_type IN ('NORMAL','LAB','MULTIMEDIA')", name="ck_classrooms_type"
        ),
        CheckConstraint(
            "status IN ('ACTIVE','MAINTENANCE','DISABLED')", name="ck_classrooms_status"
        ),
        CheckConstraint("capacity > 0", name="ck_classrooms_capacity"),
        Index("idx_classrooms_building", "building"),
        {**_KW, "comment": "教室"},
    )

    code: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    building: Mapped[str] = mapped_column(String(50), nullable=False, comment="楼栋")
    capacity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    room_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="NORMAL", server_default="NORMAL"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )

    def __repr__(self) -> str:
        return f"<Classroom {self.code}>"
