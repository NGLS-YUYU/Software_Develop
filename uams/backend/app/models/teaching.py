"""开课与排课：教学任务、教学班、排课（DATABASE.md §7）。"""

from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import BIGINT, TINYINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.course import Course
    from app.models.organization import Classroom, College
    from app.models.person import Teacher

_KW = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


class SelectionStatus:
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    FINISHED = "FINISHED"


class WeekType:
    ALL = "ALL"
    ODD = "ODD"
    EVEN = "EVEN"


class TeachingTask(Base, IdMixin, TimestampMixin):
    __tablename__ = "teaching_tasks"
    __table_args__ = (
        UniqueConstraint("semester", "course_id", "college_id", name="uk_teaching_tasks"),
        CheckConstraint(
            "status IN ('DRAFT','CONFIRMED','CANCELLED')", name="ck_teaching_tasks_status"
        ),
        Index("idx_teaching_tasks_semester", "semester"),
        {**_KW, "comment": "教学任务"},
    )

    semester: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="学期，如 2026-2027-1"
    )
    course_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("courses.id", ondelete="RESTRICT", name="fk_tt_course"),
        nullable=False,
    )
    college_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("colleges.id", ondelete="RESTRICT", name="fk_tt_college"),
        nullable=False, comment="承担学院",
    )
    planned_classes: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default="1", comment="计划开班数"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", server_default="DRAFT"
    )

    course: Mapped["Course"] = relationship()
    college: Mapped["College"] = relationship()
    teaching_classes: Mapped[list["TeachingClass"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class TeachingClass(Base, IdMixin, TimestampMixin):
    """教学班：选课、排课、成绩、考试的公共锚点。"""

    __tablename__ = "teaching_classes"
    __table_args__ = (
        CheckConstraint(
            "selection_status IN ('CLOSED','OPEN','FINISHED')", name="ck_tc_sel"
        ),
        CheckConstraint("status IN ('ACTIVE','CANCELLED')", name="ck_tc_status"),
        CheckConstraint("capacity > 0", name="ck_tc_capacity"),
        CheckConstraint("selected_count >= 0", name="ck_tc_count"),
        Index("idx_tc_semester_course", "semester", "course_id"),
        Index("idx_tc_teacher", "teacher_id"),
        Index("idx_tc_selection", "selection_status", "semester"),
        {**_KW, "comment": "教学班"},
    )

    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    task_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("teaching_tasks.id", ondelete="CASCADE", name="fk_tc_task"),
        nullable=False,
    )
    # course_id / semester 为有意冗余，避免课表等高频查询三表 JOIN（DATABASE.md §13.3）
    course_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("courses.id", ondelete="RESTRICT", name="fk_tc_course"),
        nullable=False,
    )
    semester: Mapped[str] = mapped_column(String(16), nullable=False)
    teacher_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("teachers.id", ondelete="RESTRICT", name="fk_tc_teacher"),
        nullable=True, comment="授课教师，排课前可为空",
    )
    capacity: Mapped[int] = mapped_column(SmallInteger, nullable=False, comment="容量上限")
    selected_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0",
        comment="已选人数；必须在事务内与选课记录同步",
    )
    selection_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="CLOSED", server_default="CLOSED"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )

    task: Mapped["TeachingTask"] = relationship(back_populates="teaching_classes")
    course: Mapped["Course"] = relationship()
    teacher: Mapped["Teacher | None"] = relationship()
    schedules: Mapped[list["Schedule"]] = relationship(
        back_populates="teaching_class", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<TeachingClass {self.code}>"


class Schedule(Base, IdMixin, TimestampMixin):
    __tablename__ = "schedules"
    __table_args__ = (
        CheckConstraint("day_of_week BETWEEN 1 AND 7", name="ck_schedules_day"),
        CheckConstraint(
            "start_period >= 1 AND end_period >= start_period", name="ck_schedules_period"
        ),
        CheckConstraint(
            "start_week >= 1 AND end_week >= start_week", name="ck_schedules_week"
        ),
        CheckConstraint("week_type IN ('ALL','ODD','EVEN')", name="ck_schedules_wtype"),
        Index("idx_schedules_tc", "teaching_class_id"),
        Index("idx_schedules_conflict", "semester", "day_of_week", "classroom_id"),
        Index("idx_schedules_time", "semester", "day_of_week", "start_period", "end_period"),
        {**_KW, "comment": "排课"},
    )

    teaching_class_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("teaching_classes.id", ondelete="CASCADE", name="fk_sched_tc"),
        nullable=False,
    )
    classroom_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("classrooms.id", ondelete="RESTRICT", name="fk_sched_room"),
        nullable=False,
    )
    day_of_week: Mapped[int] = mapped_column(
        TINYINT(unsigned=True), nullable=False, comment="1=周一 … 7=周日"
    )
    start_period: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False)
    end_period: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False)
    start_week: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False)
    end_week: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False)
    week_type: Mapped[str] = mapped_column(
        String(10), nullable=False, default="ALL", server_default="ALL",
        comment="ALL / ODD / EVEN",
    )
    semester: Mapped[str] = mapped_column(String(16), nullable=False)

    teaching_class: Mapped["TeachingClass"] = relationship(back_populates="schedules")
    classroom: Mapped["Classroom"] = relationship()

    def overlaps(self, other: "Schedule") -> bool:
        """判断两条排课是否冲突（DATABASE.md §7.3）。"""
        if self.semester != other.semester or self.day_of_week != other.day_of_week:
            return False
        if not (self.start_period <= other.end_period and other.start_period <= self.end_period):
            return False
        if not (self.start_week <= other.end_week and other.start_week <= self.end_week):
            return False
        # 单双周相容：任一为 ALL，或两者相同
        if WeekType.ALL in (self.week_type, other.week_type):
            return True
        return self.week_type == other.week_type
