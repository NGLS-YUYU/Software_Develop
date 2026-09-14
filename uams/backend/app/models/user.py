"""用户模型（DATABASE.md §3.1）。"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    SmallInteger,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.role import Role


class UserType:
    STUDENT = "STUDENT"
    TEACHER = "TEACHER"
    ADMIN = "ADMIN"
    ALL = (STUDENT, TEACHER, ADMIN)


class UserStatus:
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    LOCKED = "LOCKED"
    ALL = (ACTIVE, DISABLED, LOCKED)


class User(Base, IdMixin, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "user_type IN ('STUDENT','TEACHER','ADMIN')", name="ck_users_type"
        ),
        CheckConstraint(
            "status IN ('ACTIVE','DISABLED','LOCKED')", name="ck_users_status"
        ),
        Index("idx_users_type_status", "user_type", "status"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
            "comment": "统一用户账号",
        },
    )

    username: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, comment="登录名；学生为学号，教师为工号"
    )
    # bcrypt 哈希固定 60 字符，留到 255 以便将来更换算法（CLAUDE.md §23：禁止明文）
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="密码哈希"
    )
    real_name: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="真实姓名"
    )
    user_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="STUDENT / TEACHER / ADMIN"
    )
    email: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True, comment="邮箱"
    )
    phone: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="手机号"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=UserStatus.ACTIVE,
        server_default=UserStatus.ACTIVE, comment="账号状态",
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="最后登录时间"
    )
    failed_login_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0",
        comment="连续登录失败次数",
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="锁定到期时间"
    )

    roles: Mapped[list["Role"]] = relationship(
        secondary="user_roles", back_populates="users", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.user_type})>"
