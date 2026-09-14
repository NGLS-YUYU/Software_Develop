"""角色与权限模型（DATABASE.md §3.2 - §3.5）。"""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User

_TABLE_KW = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


class RoleCode:
    """第一阶段仅三个角色（CLAUDE.md §8）。"""

    STUDENT = "STUDENT"
    TEACHER = "TEACHER"
    ACADEMIC_ADMIN = "ACADEMIC_ADMIN"
    ALL = (STUDENT, TEACHER, ACADEMIC_ADMIN)


class Role(Base, IdMixin, TimestampMixin):
    __tablename__ = "roles"
    __table_args__ = ({**_TABLE_KW, "comment": "系统角色"},)

    code: Mapped[str] = mapped_column(
        String(30), nullable=False, unique=True, comment="角色代码"
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="角色名称")
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_builtin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0",
        comment="内置角色不可删除",
    )

    users: Mapped[list["User"]] = relationship(
        secondary="user_roles", back_populates="roles"
    )
    permissions: Mapped[list["Permission"]] = relationship(
        secondary="role_permissions", back_populates="roles", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Role {self.code}>"


class Permission(Base, IdMixin, TimestampMixin):
    __tablename__ = "permissions"
    __table_args__ = (
        Index("idx_permissions_module", "module"),
        {**_TABLE_KW, "comment": "系统权限"},
    )

    code: Mapped[str] = mapped_column(
        String(80), nullable=False, unique=True, comment="权限码，格式 <资源>:<动作>"
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False, comment="权限名称")
    module: Mapped[str] = mapped_column(
        String(40), nullable=False, comment="所属模块"
    )
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)

    roles: Mapped[list["Role"]] = relationship(
        secondary="role_permissions", back_populates="permissions"
    )

    def __repr__(self) -> str:
        return f"<Permission {self.code}>"


class UserRole(Base, IdMixin):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uk_user_roles"),
        {**_TABLE_KW, "comment": "用户-角色关联"},
    )

    user_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_user_roles_user"),
        nullable=False,
    )
    role_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("roles.id", ondelete="CASCADE", name="fk_user_roles_role"),
        nullable=False,
    )


class RolePermission(Base, IdMixin):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uk_role_permissions"),
        {**_TABLE_KW, "comment": "角色-权限关联"},
    )

    role_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("roles.id", ondelete="CASCADE", name="fk_role_perms_role"),
        nullable=False,
    )
    permission_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("permissions.id", ondelete="CASCADE", name="fk_role_perms_perm"),
        nullable=False,
    )
