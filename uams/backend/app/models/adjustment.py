"""调停课申请（F-22）。"""
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.dialects.mysql import BIGINT, TINYINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.organization import Classroom
    from app.models.teaching import Schedule, TeachingClass
    from app.models.user import User

_KW = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


class AdjustmentStatus:
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class AdjustmentType:
    CHANGE = "CHANGE"
    CANCEL = "CANCEL"
    ADD = "ADD"


class ScheduleAdjustment(Base, IdMixin, TimestampMixin):
    __tablename__ = "schedule_adjustments"
    __table_args__ = (
        CheckConstraint("request_type IN ('CHANGE','CANCEL','ADD')", name="ck_adj_type"),
        CheckConstraint("status IN ('PENDING','APPROVED','REJECTED')", name="ck_adj_status"),
        Index("idx_adj_status", "status", "created_at"),
        Index("idx_adj_class", "teaching_class_id"),
        {**_KW, "comment": "调停课申请"},
    )

    teaching_class_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("teaching_classes.id", ondelete="CASCADE", name="fk_adj_class"),
        nullable=False,
    )
    schedule_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("schedules.id", ondelete="SET NULL", name="fk_adj_schedule"),
        nullable=True,
    )
    request_type: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    new_day_of_week: Mapped[int | None] = mapped_column(TINYINT(unsigned=True), nullable=True)
    new_start_period: Mapped[int | None] = mapped_column(TINYINT(unsigned=True), nullable=True)
    new_end_period: Mapped[int | None] = mapped_column(TINYINT(unsigned=True), nullable=True)
    new_start_week: Mapped[int | None] = mapped_column(TINYINT(unsigned=True), nullable=True)
    new_end_week: Mapped[int | None] = mapped_column(TINYINT(unsigned=True), nullable=True)
    new_week_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    new_classroom_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("classrooms.id", ondelete="SET NULL", name="fk_adj_room"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AdjustmentStatus.PENDING,
        server_default=AdjustmentStatus.PENDING,
    )
    requested_by: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_adj_requester"),
        nullable=True,
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_adj_reviewer"),
        nullable=True,
    )
    review_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    teaching_class: Mapped["TeachingClass"] = relationship()
    schedule: Mapped["Schedule | None"] = relationship()
    classroom: Mapped["Classroom | None"] = relationship()
    requester: Mapped["User | None"] = relationship(foreign_keys=[requested_by])
    reviewer: Mapped["User | None"] = relationship(foreign_keys=[reviewed_by])
