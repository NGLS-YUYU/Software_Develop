"""考试（DATABASE.md §10）。"""

from datetime import date, time
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.course import Course
    from app.models.organization import Classroom
    from app.models.person import Student, Teacher
    from app.models.teaching import TeachingClass

_KW = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


class ExamType:
    FINAL = "FINAL"      # 期末
    MAKEUP = "MAKEUP"    # 补考
    RETAKE = "RETAKE"    # 重修


class Exam(Base, IdMixin, TimestampMixin):
    __tablename__ = "exams"
    __table_args__ = (
        CheckConstraint("exam_type IN ('FINAL','MAKEUP','RETAKE')", name="ck_exams_type"),
        CheckConstraint(
            "status IN ('DRAFT','PUBLISHED','FINISHED')", name="ck_exams_status"
        ),
        CheckConstraint("end_time > start_time", name="ck_exams_time"),
        Index("idx_exams_date", "exam_date", "start_time"),
        Index("idx_exams_tc", "teaching_class_id"),
        {**_KW, "comment": "考试"},
    )

    teaching_class_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("teaching_classes.id", ondelete="CASCADE", name="fk_exams_tc"),
        nullable=False,
    )
    course_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("courses.id", ondelete="RESTRICT", name="fk_exams_course"),
        nullable=False,
    )
    semester: Mapped[str] = mapped_column(String(16), nullable=False)
    exam_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ExamType.FINAL, server_default=ExamType.FINAL
    )
    exam_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", server_default="DRAFT"
    )

    teaching_class: Mapped["TeachingClass"] = relationship()
    course: Mapped["Course"] = relationship()
    rooms: Mapped[list["ExamRoom"]] = relationship(
        back_populates="exam", cascade="all, delete-orphan"
    )


class ExamRoom(Base, IdMixin, TimestampMixin):
    __tablename__ = "exam_rooms"
    __table_args__ = (
        UniqueConstraint("exam_id", "classroom_id", name="uk_exam_rooms"),
        CheckConstraint("capacity > 0", name="ck_exam_rooms_capacity"),
        {**_KW, "comment": "考场"},
    )

    exam_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("exams.id", ondelete="CASCADE", name="fk_er_exam"),
        nullable=False,
    )
    classroom_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("classrooms.id", ondelete="RESTRICT", name="fk_er_room"),
        nullable=False,
    )
    capacity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    assigned_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )
    invigilator_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("teachers.id", ondelete="SET NULL", name="fk_er_invigilator"),
        nullable=True, comment="监考教师",
    )

    exam: Mapped["Exam"] = relationship(back_populates="rooms")
    classroom: Mapped["Classroom"] = relationship()
    students: Mapped[list["ExamStudent"]] = relationship(
        back_populates="room", cascade="all, delete-orphan"
    )


class ExamStudent(Base, IdMixin, TimestampMixin):
    __tablename__ = "exam_students"
    __table_args__ = (
        UniqueConstraint("exam_room_id", "student_id", name="uk_exam_students"),
        Index("idx_exam_students_student", "student_id"),
        {**_KW, "comment": "考场学生分配"},
    )

    exam_room_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("exam_rooms.id", ondelete="CASCADE", name="fk_es_room"),
        nullable=False,
    )
    student_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("students.id", ondelete="CASCADE", name="fk_es_student"),
        nullable=False,
    )
    seat_no: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    room: Mapped["ExamRoom"] = relationship(back_populates="students")
    student: Mapped["Student"] = relationship()
