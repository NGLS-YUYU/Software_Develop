"""教学评价、通知公告、操作日志（DATABASE.md §11 - §12）。"""

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
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.person import Student, Teacher
    from app.models.teaching import TeachingClass
    from app.models.user import User

_KW = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


class EvaluationTask(Base, IdMixin, TimestampMixin):
    __tablename__ = "evaluation_tasks"
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="ck_eval_task_time"),
        CheckConstraint(
            "status IN ('PENDING','ACTIVE','CLOSED')", name="ck_eval_task_status"
        ),
        Index("idx_eval_tasks_sem", "semester", "status"),
        {**_KW, "comment": "教学评价任务"},
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    semester: Mapped[str] = mapped_column(String(16), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING", server_default="PENDING"
    )

    def is_open_now(self) -> bool:
        return self.status == "ACTIVE" and self.start_time <= datetime.now() <= self.end_time


class Evaluation(Base, IdMixin, TimestampMixin):
    """学生对教学班的评价。

    表中保留 student_id 仅用于防重复提交；
    教师端与统计接口不得下发该字段（PRD §8.8 匿名性要求）。
    """

    __tablename__ = "evaluations"
    __table_args__ = (
        UniqueConstraint(
            "task_id", "student_id", "teaching_class_id", name="uk_evaluations"
        ),
        CheckConstraint("score BETWEEN 0 AND 100", name="ck_evaluations_score"),
        Index("idx_evaluations_teacher", "teacher_id"),
        Index("idx_evaluations_tc", "teaching_class_id"),
        {**_KW, "comment": "教学评价"},
    )

    task_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("evaluation_tasks.id", ondelete="CASCADE", name="fk_eval_task"),
        nullable=False,
    )
    student_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("students.id", ondelete="CASCADE", name="fk_eval_student"),
        nullable=False,
    )
    teaching_class_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("teaching_classes.id", ondelete="CASCADE", name="fk_eval_tc"),
        nullable=False,
    )
    teacher_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("teachers.id", ondelete="RESTRICT", name="fk_eval_teacher"),
        nullable=False,
    )
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    teaching_class: Mapped["TeachingClass"] = relationship()
    teacher: Mapped["Teacher"] = relationship()


class Announcement(Base, IdMixin, TimestampMixin):
    __tablename__ = "announcements"
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('ALL','STUDENT','TEACHER')", name="ck_ann_target"
        ),
        CheckConstraint(
            "status IN ('DRAFT','PUBLISHED','WITHDRAWN')", name="ck_ann_status"
        ),
        Index("idx_announcements_pub", "status", "target_type", "published_at"),
        {**_KW, "comment": "通知公告"},
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ALL", server_default="ALL"
    )
    publisher_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_ann_publisher"),
        nullable=False,
    )
    is_top: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", server_default="DRAFT"
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    publisher: Mapped["User"] = relationship()


class OperationLog(Base, IdMixin):
    """操作日志（CLAUDE.md §24）。

    禁止记录密码、令牌等敏感信息。
    """

    __tablename__ = "operation_logs"
    __table_args__ = (
        CheckConstraint("result IN ('SUCCESS','FAILURE')", name="ck_oplogs_result"),
        Index("idx_oplogs_user_time", "user_id", "created_at"),
        Index("idx_oplogs_action_time", "action", "created_at"),
        Index("idx_oplogs_resource", "resource_type", "resource_id"),
        {**_KW, "comment": "操作日志"},
    )

    user_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_oplogs_user"),
        nullable=True, comment="登录失败时可能为空",
    )
    username: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="冗余快照，用户删除后仍可追溯"
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    module: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resource_id: Mapped[int | None] = mapped_column(BIGINT(unsigned=True), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(
        String(45), nullable=True, comment="兼容 IPv6"
    )
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    result: Mapped[str] = mapped_column(
        String(20), nullable=False, default="SUCCESS", server_default="SUCCESS"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
